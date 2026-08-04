"""Ops brief — the one Discord "Morning Brief" embed, built from the engine's synthetic outputs.

Synthetic data only (data/*.csv via the engine modules). The Discord payload format ships *here*,
in the engine, so it's versioned alongside the logic that produces the numbers — the wording and
the verdict thresholds move together in one commit, not in a separate scheduler config.

The scheduler that actually posts this is a dumb fetch-and-post: it GETs this brief and POSTs each
message to a Discord webhook, batching at <= 1 request / 1.5s to stay under the webhook rate limit.
That batching / retry / webhook-URL handling is the scheduler's job, NOT this module's — this module
never touches the network, never sees a webhook URL, and just returns a ready-to-post embed.

`ops_brief()` returns {"messages": [<discord_embed>]} and is wrapped so it never raises: a dead feed
drops its own field rather than sinking the whole brief.
"""
from datetime import datetime


def _fit(lines, limit=1024, more="… plus {n} more on the dashboard"):
    """Join lines with newlines, dropping whole lines from the end until it fits `limit`, appending a
    "+N more" tail for whatever was dropped. Whole lines only — never a mid-sentence slice."""
    kept = list(lines)
    while kept:
        dropped = len(lines) - len(kept)
        text = "\n".join(kept + ([more.format(n=dropped)] if dropped else []))
        if len(text) <= limit:
            return text
        kept.pop()
    return more.format(n=len(lines))


def _handle(h):
    """@ hygiene — display a handle as exactly one leading @."""
    return "@" + str(h).lstrip("@")


import re as _re

# a sentence-ending period is one followed by whitespace/end — NOT a decimal point like $1.85 or 2.10
_SENT_END = _re.compile(r"\.(?=\s|$)")


def _first_sentence(instr):
    """Strip a leading '→ ' and take the first sentence, without splitting a decimal (e.g. $1.85)."""
    s = str(instr)
    if s.startswith("→"):
        s = s[1:].lstrip()
    s = s.strip()
    m = _SENT_END.search(s)
    return (s[:m.end()] if m else s).strip()


def _instruction(item):
    """The exact instruction from a queue item's why-lines: the last line if it starts with '→'."""
    why = item.get("why") or []
    if why and str(why[-1]).lstrip().startswith("→"):
        return why[-1]
    return ""


def ops_brief():
    """Build the single Morning-Brief Discord embed. Never raises — each source is guarded so a dead
    feed drops its field, not the brief. Returns {"messages": [embed]}."""
    embed = {
        "title": "☀️ Morning Brief — " + datetime.utcnow().strftime("%b %d").replace(" 0", " "),
        "color": 0x0ca30c,
        "description": "",
        "fields": [],
        "footer": {"text": "⚡ verdict flips · 🔥 boost windows · 🔔 heads-ups arrive separately, "
                           "only when something changes."},
    }

    # --- decision queue -------------------------------------------------------
    queue = []
    try:
        from app.decide import decision_queue
        queue = decision_queue().get("queue", []) or []
    except Exception:
        queue = []

    campaigns = [q for q in queue if q.get("type") == "campaign"]
    sparks = [q for q in queue if q.get("type") == "spark"]

    losing_actions = {"CUT", "GATE", "PAUSED"}
    tune_actions = {"TUNE", "RETARGET"}

    # --- color from campaign verdicts ----------------------------------------
    camp_actions = {str(c.get("action", "")).upper() for c in campaigns}
    if camp_actions & losing_actions:
        embed["color"] = 0xd03b3b
    elif camp_actions & tune_actions:
        embed["color"] = 0xb97f00
    else:
        embed["color"] = 0x0ca30c

    # --- recommend candidates -------------------------------------------------
    candidates, excluded = [], {}
    try:
        from app.recommend import recommend
        r = recommend(n=12)
        candidates = r.get("candidates", []) or []
        excluded = r.get("excluded", {}) or {}
    except Exception:
        candidates = []

    # --- description topline counts ------------------------------------------
    losing = sum(1 for c in campaigns if str(c.get("action", "")).upper() in losing_actions)
    tune = sum(1 for c in campaigns if str(c.get("action", "")).upper() in tune_actions)
    boost = sum(1 for s in sparks if str(s.get("action", "")).upper() == "SPARK NOW")
    seed = sum(1 for c in candidates if not c.get("cold_start") and int(c.get("rank", 9999)) <= 25)
    if losing or tune or boost or seed:
        embed["description"] = (f"**{losing}** campaigns losing money · **{tune}** need a settings change · "
                                f"**{boost}** videos worth boosting · **{seed}** creators ready to sample")
    else:
        embed["description"] = "Quiet day — nothing on fire. Ship your strongest picks and move on."

    # --- 📌 Do today: top 3 queue items overall ------------------------------
    do_lines = []
    for item in queue[:3]:
        if item.get("type") == "campaign":
            do_lines.append(_first_sentence(_instruction(item)))
        else:
            tgt = item.get("target", "")
            if item.get("type") == "spark":
                tgt = _handle(tgt)
            do_lines.append(f"{item.get('action', '')} {tgt}".strip())
    do_lines = [l for l in do_lines if l]
    if do_lines:
        embed["fields"].append({"name": "📌 Do today", "value": _fit(do_lines), "inline": False})

    # --- 📈 Campaigns — the money view ---------------------------------------
    camp_emoji = {"CUT": "🔴", "GATE": "🔴", "PAUSED": "🔴", "TUNE": "🟡", "RETARGET": "🟡", "SCALE": "🟢"}
    money_lines = []
    for c in campaigns[:6]:
        act = str(c.get("action", "")).upper()
        emoji = camp_emoji.get(act, "🟢")
        short = _first_sentence(_instruction(c))
        money_lines.append(f"{emoji} **{c.get('target', '')}** — {short}")
    if money_lines:
        embed["fields"].append({"name": "📈 Campaigns — the money view",
                                "value": _fit(money_lines), "inline": False})

    # --- 🗣 Customer voice ----------------------------------------------------
    voice_lines = []
    try:
        from app.report import intent_week
        iw = intent_week(days=10)
        themes = iw.get("themes") or []
        if themes:
            t = themes[0]
            voice_lines.append(f"{t.get('theme')}: {t.get('n')} comments this week — "
                               f"“{t.get('quote')}”")
    except Exception:
        pass
    try:
        from app.voc import voc
        board = voc().get("competitor_board") or []
        if board:
            top = board[0]
            voice_lines.append(f"Most-compared brand: {top.get('competitor')} ({top.get('mentions')})")
    except Exception:
        pass
    if voice_lines:
        embed["fields"].append({"name": "🗣 Customer voice", "value": _fit(voice_lines), "inline": False})

    # --- 🎯 Who to sample next -----------------------------------------------
    if candidates:
        sample_lines, n_strong = [], 0
        for c in candidates[:8]:
            rank = int(c.get("rank", 9999))
            if rank <= 10:
                tier = "🟢"
                n_strong += 1
            elif rank <= 25:
                tier = "🟡"
            else:
                tier = "⚪"
            sample_lines.append(f"{tier} {_handle(c.get('handle', ''))}")
        sample_lines.append(f"{n_strong} strong bets ready — 🟢 proven pattern, 🟡 decent shot, "
                            f"⚪ discovery.")
        embed["fields"].append({"name": "🎯 Who to sample next",
                                "value": _fit(sample_lines), "inline": False})

    # --- 🧠 The model ---------------------------------------------------------
    try:
        from app.recommender_eval import recommender_scorecard
        sc = recommender_scorecard()
        if sc and sc.get("rank_ic") is not None:
            embed["fields"].append({
                "name": "🧠 The model",
                "value": _fit([f"prediction skill {sc.get('rank_ic')} (negative = it ranks winners above "
                               f"losers) · learning from {sc.get('n')} real outcomes."]),
                "inline": False})
    except Exception:
        pass

    return {"messages": [embed]}
