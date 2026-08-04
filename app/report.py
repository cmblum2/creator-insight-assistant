"""One-click weekly Agency Report (synthetic twin).

Turns the live analytics into a printable artifact a non-technical team can act on:
level AND direction (sparklines + MoM), decisions with exact instructions, problems ranked
by dollars at stake, a maturation-aware trend desk, a forward-30-days plan, weekly
voice-of-customer, and a model-diagnostics appendix.

Everything renders from this repo's SYNTHETIC data (scripts/gen_data.py) — no real handles,
brands, or figures. Data assembly is guarded per-source: a broken feed costs one section, not
the report. PDF rendering shells out to an installed Chrome/Chromium (--print-to-pdf); if none
is present, /report (HTML) still works and the reader prints from the browser.

Portable framework spec: docs/REPORT-FRAMEWORK.md.
"""
import html as _html
import os
import shutil
import subprocess
import tempfile
import threading
import time
from datetime import date, datetime
from pathlib import Path

import pandas as pd

from app.config import CONTRACT, SAMPLE_COST

AS_OF = "2026-07-30"   # the synthetic data's fixed "as of" date (TODAY in gen_data.py)

# ── formatters — every one tolerates None/blank → "—" so a missing number never crashes ──────
def money(v):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return "—"
    return f"-${abs(v):,.0f}" if v < 0 else f"${v:,.0f}"


def pct(v, digits=0):
    try:
        return f"{float(v) * 100:.{digits}f}%"
    except (TypeError, ValueError):
        return "—"


def num(v, digits=2):
    try:
        return f"{float(v):,.{digits}f}"
    except (TypeError, ValueError):
        return "—"


def esc(v):
    return _html.escape("" if v is None else str(v))


def at(h):
    h = str(h or "").lstrip("@")
    return "@" + h if h else "—"


def _f(v):
    """Coerce to float or None (blank/NaN-safe)."""
    try:
        if v is None or (isinstance(v, float) and pd.isna(v)) or v == "":
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


# ── quant marks ──────────────────────────────────────────────────────────────────────────────
BLUE = "#2a78d6"
STATUS = {"good": "#0ca30c", "warning": "#b97f00", "serious": "#c05a2e", "critical": "#d03b3b",
          "neutral": "#52514e", "data": BLUE}


def spark_svg(vals, w=70, h=18, hue=BLUE):
    vals = [v for v in (_f(x) for x in vals) if v is not None]
    if len(vals) < 2:
        return ""
    lo, hi = min(vals), max(vals)
    rng = (hi - lo) or 1.0
    n = len(vals)
    pts = [(1 + i * (w - 4) / (n - 1), h - 2 - (v - lo) * (h - 5) / rng) for i, v in enumerate(vals)]
    poly = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    ex, ey = pts[-1]
    return (f'<svg class="spark" width="{w}" height="{h}" viewBox="0 0 {w} {h}">'
            f'<polyline fill="none" stroke="{hue}" stroke-width="1.3" points="{poly}"/>'
            f'<circle cx="{ex:.1f}" cy="{ey:.1f}" r="1.8" fill="{hue}"/></svg>')


def mom(cur, prev, good_up=True):
    cur, prev = _f(cur), _f(prev)
    if cur is None or prev is None or prev == 0:
        return ""
    ch = (cur - prev) / abs(prev)
    good = (ch >= 0) == good_up
    col = STATUS["good"] if good else STATUS["critical"]
    arrow = "▲" if ch >= 0 else "▼"
    return f'<span class="delta" style="color:{col}">{arrow} {abs(ch) * 100:.0f}%</span>'


def trajectory(vals, good_up=True):
    vs = [v for v in (_f(x) for x in vals) if v is not None]
    if len(vs) < 2:
        return "—"
    n = len(vs)
    xs = list(range(n))
    mx, my = sum(xs) / n, sum(vs) / n
    denom = sum((x - mx) ** 2 for x in xs) or 1.0
    slope = sum((xs[i] - mx) * (vs[i] - my) for i in range(n)) / denom
    mean = (sum(abs(v) for v in vs) / n) or 1.0
    rel = slope / mean
    if abs(rel) < 0.03:
        return "flat"
    return "improving" if (slope > 0) == good_up else "deteriorating"


# ── markup helpers — helpers emit markup; callers pass text (which we escape) ─────────────────
def chip(label, status="neutral"):
    c = STATUS.get(status, STATUS["neutral"])
    # tinted pill (survives print via print-color-adjust:exact in the CSS)
    return f'<span class="chip" style="color:{c};background:{c}1a;border:1px solid {c}55">{esc(label)}</span>'


def verdict_status(v):
    return {"SCALE": "good", "SPARK NOW": "good", "SAMPLE": "data",
            "TUNE": "warning", "WATCH": "warning", "REVIVE?": "warning",
            "RETARGET": "serious", "HOLD": "neutral", "PAUSED": "neutral",
            "CUT": "critical", "GATE": "critical"}.get(str(v).upper(), "neutral")


def tile(label, value, sub="", accent=False):
    a = ' style="color:%s"' % BLUE if accent else ""
    return (f'<div class="tile"><div class="t-label">{esc(label)}</div>'
            f'<div class="t-value"{a}>{value}</div><div class="t-sub">{sub}</div></div>')


def qtile(label, value, spark="", delta="", sub=""):
    return (f'<div class="tile"><div class="t-label">{esc(label)}</div>'
            f'<div class="t-value">{value} <span class="t-mark">{spark}{delta}</span></div>'
            f'<div class="t-sub">{sub}</div></div>')


def table(headers, rows, right=()):
    ths = "".join(f'<th class="{"r" if i in right else ""}">{esc(h)}</th>' for i, h in enumerate(headers))
    body = ""
    for r in rows:
        tds = "".join(f'<td class="{"r" if i in right else ""}">{c}</td>' for i, c in enumerate(r))
        body += f"<tr>{tds}</tr>"
    return f'<table><thead><tr>{ths}</tr></thead><tbody>{body}</tbody></table>'


def bar(frac, label="", hue=BLUE):
    f = _f(frac)
    f = 0.0 if f is None else max(0.0, min(1.0, f))
    return (f'<div class="bar"><div class="bar-fill" style="width:{f * 100:.0f}%;background:{hue}"></div>'
            f'<span class="bar-label">{esc(label)}</span></div>')


def signed_bar(frac, label="", hue=BLUE):
    """Center-anchored bar for signed importance (−1..1)."""
    f = _f(frac) or 0.0
    f = max(-1.0, min(1.0, f))
    w = abs(f) * 50.0
    left = 50.0 if f >= 0 else 50.0 - w
    return (f'<div class="bar signed"><div class="bar-mid"></div>'
            f'<div class="bar-fill" style="left:{left:.0f}%;width:{w:.0f}%;background:{hue}"></div>'
            f'<span class="bar-label">{esc(label)}</span></div>')


def note_row(d, *keys):
    """If d is missing/None/only a note, return the honest italic line; else None."""
    if not isinstance(d, dict):
        return '<p class="unavail">unavailable</p>'
    if "note" in d and not any(k in d for k in keys):
        return f'<p class="unavail">unavailable — {esc(d["note"])}</p>'
    return None


def section(title, body, sub="", page_break=True, idx=None, tag=None, read=None):
    pb = " pb" if page_break else ""
    n = f'<span class="s-num">{esc(idx)}</span>' if idx else ""
    tg = f'<span class="s-tag t-{tag.lower()}">{esc(tag)}</span>' if tag else ""
    s = f'<div class="s-sub">{esc(sub)}</div>' if sub else ""
    rd = f'<div class="s-read"><span class="rl">THE READ</span> {esc(read)}</div>' if read else ""
    return (f'<section class="sec{pb}">{n}<div class="s-head"><h2>{esc(title)}</h2>{tg}</div>'
            f'{s}{rd}{body}</section>')


# ── data helpers that read CSVs directly (weekly VoC views) ──────────────────────────────────
_CAT_LABEL = {"purchase": "Buy-intent", "confirmed_purchase": "Confirmed purchase",
              "price": "Price pushback", "comparison": "Competitor comparison", "praise": "Praise"}


def intent_week(days=10):
    """Themes of the week: comments scraped in the last N days → theme counts + top-liked quote each."""
    cm = pd.read_csv(CONTRACT["comments"])
    cm["scraped_at"] = pd.to_datetime(cm["scraped_at"], errors="coerce")
    asof = pd.to_datetime(AS_OF)
    win = cm[(cm["scraped_at"].notna()) & (cm["scraped_at"] >= asof - pd.Timedelta(days=days))]
    total = int(len(win))
    if not total:
        return {"note": "no comments in window"}
    themes = []
    for cat, g in win.groupby("category"):
        top = g.sort_values("like_count", ascending=False).iloc[0]
        themes.append({"theme": _CAT_LABEL.get(cat, cat), "n": int(len(g)),
                       "share": len(g) / total, "quote": str(top["comment_text"])[:170],
                       "handle": str(top["handle"]), "likes": int(top["like_count"])})
    themes.sort(key=lambda x: -x["n"])
    return {"window_days": days, "total": total, "themes": themes}


def voc_campaigns(verdict_map):
    """Comments grouped per campaign (comment → video → campaign_id), with verdict from the queue."""
    cm = pd.read_csv(CONTRACT["comments"])[["video_id", "category", "comment_text", "like_count", "handle"]]
    vids = pd.read_csv(CONTRACT["videos"])[["video_id", "campaign_id"]]
    camps = pd.read_csv(CONTRACT["campaigns"])[["campaign_id", "campaign_name"]]
    j = cm.merge(vids, on="video_id").merge(camps, on="campaign_id")
    out = []
    for cid, g in j.groupby("campaign_id"):
        name = str(g["campaign_name"].iloc[0])
        mix = g["category"].value_counts()
        top_themes = [f"{_CAT_LABEL.get(k, k)} {v}" for k, v in mix.head(3).items()]
        quotes = [{"text": str(r["comment_text"])[:170], "handle": str(r["handle"]), "likes": int(r["like_count"])}
                  for _, r in g.sort_values("like_count", ascending=False).head(2).iterrows()]
        out.append({"campaign": name, "verdict": verdict_map.get(str(cid), ""),
                    "n": int(len(g)), "themes": top_themes, "quotes": quotes})
    out.sort(key=lambda x: -x["n"])
    return out[:8]


def monthly():
    """Monthly cohort series as list of dicts; blank outcome cells → None (immature)."""
    df = pd.read_csv(CONTRACT["monthly_trends"])
    rows = []
    for _, r in df.iterrows():
        rows.append({"month": str(r["month"]), "samples": _f(r["samples"]),
                     "gmv": _f(r["gmv"]), "profit": _f(r["profit"]), "win_rate": _f(r["win_rate"])})
    return rows


# ── assembly — one guarded grab per source ───────────────────────────────────────────────────
def build_report_data(budget=50000):
    out = {}

    def grab(key, fn):
        try:
            out[key] = fn()
        except Exception as e:
            out[key] = {"note": f"unavailable: {str(e)[:140]}"}

    grab("decisions", lambda: __import__("app.decide", fromlist=["decision_queue"]).decision_queue())
    grab("scorecard", lambda: __import__("app.scorecard", fromlist=["scorecard"]).scorecard())
    grab("funnel_diag", lambda: __import__("app.scorecard", fromlist=["funnel_diagnosis"]).funnel_diagnosis())
    grab("economics", lambda: __import__("app.economics", fromlist=["unit_economics"]).unit_economics())
    grab("prize", lambda: __import__("app.economics", fromlist=["size_the_prize"]).size_the_prize())
    grab("sensitivity", lambda: __import__("app.economics", fromlist=["sensitivity"]).sensitivity())
    grab("allocate", lambda: __import__("app.allocator", fromlist=["allocate"]).allocate(budget))
    grab("recommend", lambda: __import__("app.recommend", fromlist=["recommend"]).recommend(n=12))
    grab("voc", lambda: __import__("app.voc", fromlist=["voc"]).voc())
    grab("spark", lambda: __import__("app.spark", fromlist=["spark_report"]).spark_report())
    grab("post", lambda: __import__("app.post_rate", fromlist=["funnel"]).funnel())
    grab("hetero", lambda: __import__("app.heterogeneity", fromlist=["heterogeneity"]).heterogeneity())
    grab("theme_lift", lambda: __import__("app.theme_lift", fromlist=["report"]).report())
    grab("holdout", lambda: __import__("app.holdout", fromlist=["report"]).report())
    grab("drift", lambda: __import__("app.drift", fromlist=["drift_report"]).drift_report())
    grab("recommender", lambda: __import__("app.recommender_eval", fromlist=["recommender_scorecard"]).recommender_scorecard())
    grab("ltv", lambda: __import__("app.cohorts", fromlist=["ltv"]).ltv())
    grab("retention", lambda: __import__("app.cohorts", fromlist=["retention_curve"]).retention_curve())
    grab("intent_week", lambda: intent_week())
    grab("trends", monthly)
    grab("corpus", _corpus)

    # per-campaign VoC needs the verdict map from the decision queue
    vmap = {}
    dq = out.get("decisions", {})
    if isinstance(dq, dict):
        for a in dq.get("queue", []):
            if a.get("type") == "campaign" and a.get("campaign_id"):
                vmap[str(a["campaign_id"])] = a.get("action", "")
    grab("voc_campaigns", lambda: voc_campaigns(vmap))
    out["budget"] = budget
    return out


def _corpus():
    c = pd.read_csv(CONTRACT["comments"])
    return {"comments": int(len(c)), "videos": int(c["video_id"].nunique()),
            "creators": int(c["handle"].nunique())}


# ── section builders ─────────────────────────────────────────────────────────────────────────
def _header(d):
    corp = d.get("corpus", {})
    size = ("%s comments · %s videos · %s creators" %
            (f"{corp.get('comments', 0):,}", f"{corp.get('videos', 0):,}", f"{corp.get('creators', 0):,}")
            if isinstance(corp, dict) and "comments" in corp else "corpus unavailable")
    gen = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    strip = ("This system does what a status dashboard can't: measures causal lift against matched "
             "controls, re-ranks creators from its own outcomes, reads buy-intent from comment NLP, "
             "optimizes the paid-vs-sampling budget split, and monitors its own model drift.")
    return (f'<header class="rpt-head"><div class="kicker">Weekly agency report · synthetic demo</div>'
            f'<h1>Creator Sampling &amp; Campaign Desk</h1>'
            f'<div class="meta">Generated {esc(gen)} · data as of {esc(AS_OF)} · {esc(size)} · '
            f'refresh: rebuilt from synthetic source at deploy</div>'
            f'<p class="capstrip">{esc(strip)}</p></header>')


def _scoreboard(d):
    tr = d.get("trends") if isinstance(d.get("trends"), list) else []
    ser = lambda k: [r.get(k) for r in tr]
    matured = lambda k: [r.get(k) for r in tr if r.get(k) is not None]
    last2 = lambda k: (matured(k)[-2:] + [None, None])[:2]

    econ = d.get("economics", {}) if isinstance(d.get("economics"), dict) else {}
    port = econ.get("portfolio", {}) if isinstance(econ, dict) else {}
    sc = d.get("scorecard", {}) if isinstance(d.get("scorecard"), dict) else {}
    post = d.get("post", {}) if isinstance(d.get("post"), dict) else {}
    ho = d.get("holdout", {}) if isinstance(d.get("holdout"), dict) else {}
    qe = ho.get("quasi_experiment", {}) if isinstance(ho, dict) else {}
    rec = d.get("recommender", {}) if isinstance(d.get("recommender"), dict) else {}

    # matured(k)[-2:] is [prev, cur] in chronological order — unpack accordingly (latest month last)
    g_prev, g_cur = (last2("gmv") + [None, None])[:2]
    p_prev, p_cur = (last2("profit") + [None, None])[:2]
    w_prev, w_cur = (last2("win_rate") + [None, None])[:2]
    s_cur, s_prev = (ser("samples")[-1] if ser("samples") else None,
                     ser("samples")[-2] if len(ser("samples")) > 1 else None)
    mat_month = next((r["month"] for r in reversed(tr) if r.get("gmv") is not None), AS_OF)

    tiles = [
        qtile("Incremental profit (mo.)", money(p_cur), spark_svg(matured("profit")),
              mom(p_cur, p_prev), sub=f"matured cohort · as of {esc(mat_month)}"),
        qtile("Matured GMV (mo.)", money(g_cur), spark_svg(matured("gmv")),
              mom(g_cur, g_prev), sub=f"outcomes lag ~40d · as of {esc(mat_month)}"),
        qtile("Win rate", pct(w_cur), spark_svg(matured("win_rate")),
              mom(w_cur, w_prev), sub="samples that turned ROI-positive"),
        qtile("Samples shipped (mo.)", num(s_cur, 0), spark_svg(ser("samples")),
              mom(s_cur, s_prev, good_up=True), sub="volume — known immediately, not lagged"),
        tile("Portfolio ROI", num(port.get("blended_roi"), 2) + "×",
             sub="incremental profit ÷ sample spend (labeled cohort)"),
        tile("Holdout lift / sample", money(qe.get("lift")) if isinstance(qe, dict) else "—",
             sub=(f"95% CI {money(qe.get('ci_low'))}–{money(qe.get('ci_high'))}"
                  if isinstance(qe, dict) and qe.get("ci_low") is not None else "engine picks vs status quo")),
        tile("Ranker skill (rank-IC)", num(rec.get("rank_ic"), 3) if isinstance(rec, dict) else "—",
             sub="Spearman(rank, realized lift); negative = skill"),
        tile("Post rate", pct(post.get("post_rate")) if isinstance(post, dict) else "—",
             sub="shipped samples that became content"),
    ]
    body = '<div class="tiles">' + "".join(tiles) + "</div>"

    dir_word = "up" if (_f(p_cur) or 0) >= (_f(p_prev) or 0) else "down"
    read = f"Monthly incremental profit is {dir_word} to {money(p_cur)}, and {pct(w_cur)} of samples paid off."
    return section("Scoreboard", body,
                   sub="Every KPI carries a sparkline and month-over-month move; direction is colored by "
                       "whether it's good, not merely up. Lagged outcome metrics show the last matured month.",
                   page_break=False, idx="1", tag="CONTEXT", read=read)


def _three_moves(d):
    dq = d.get("decisions", {})
    queue = dq.get("queue", []) if isinstance(dq, dict) else []
    cards = []

    stops = [a for a in queue if a.get("type") == "campaign"
             and str(a.get("action", "")).upper() in ("CUT", "PAUSED", "GATE")]
    if stops:
        a = max(stops, key=lambda x: x.get("impact", 0))
        instr = next((w for w in reversed(a.get("why", [])) if str(w).lstrip().startswith("→")), "")
        cards.append(("STOP", "critical", at_or_name(a),
                      f'{chip(a.get("action"), verdict_status(a.get("action")))} {esc(a.get("title", ""))}',
                      instr))

    boosts = [a for a in queue if a.get("type") == "spark" and str(a.get("action", "")).upper() == "SPARK NOW"]
    if boosts:
        a = max(boosts, key=lambda x: x.get("impact", 0))
        instr = next((w for w in reversed(a.get("why", [])) if str(w).lstrip().startswith("→")), "")
        cards.append(("BOOST", "good", at(a.get("target")),
                      f'{chip("SPARK NOW", "good")} {esc(a.get("title", ""))}', instr))

    rec = d.get("recommend", {})
    cand = rec.get("candidates", []) if isinstance(rec, dict) else []
    strong = [c for c in cand if not c.get("cold_start") and (c.get("rank") or 999) <= 25]
    prize = d.get("prize", {})
    pps = prize.get("expected_profit_per_sample") if isinstance(prize, dict) else None
    if strong and pps is not None:
        exp = len(strong) * float(pps)
        cards.append(("SEED", "data", f"{len(strong)} strong-outlook picks",
                      f'top: {esc(", ".join(at(c.get("handle")) for c in strong[:4]))}',
                      f"→ seed all {len(strong)} · {money(pps)} expected profit/sample ≈ "
                      f"{money(exp)} expected incremental profit"))

    if not cards:
        return section("Three moves this week", '<p class="unavail">unavailable — no queued actions</p>', idx="2")
    body = '<div class="moves">'
    for tag, st, target, meta, instr in cards:
        body += (f'<div class="move"><div class="move-tag" style="color:{STATUS[st]}">{esc(tag)}</div>'
                 f'<div class="move-target">{esc(target)}</div><div class="move-meta">{meta}</div>'
                 f'<div class="instr">{esc(instr)}</div></div>')
    body += "</div>"
    read = "Three moves, ranked: stop the worst campaign, boost the best-timed video, seed the strong picks."
    return section("Three moves this week", body,
                   sub="Auto-picked from the queue: the biggest thing to stop, the best-timed boost, and the "
                       "week's seeding play sized in expected dollars.", page_break=False, idx="2",
                   tag="ACT", read=read)


def at_or_name(a):
    t = a.get("target", "")
    return at(t) if str(t).startswith("@") else esc(t)


def _problems(d):
    rows = []  # (est_dollars_or_None, area, evidence, fix)

    post = d.get("post", {})
    if isinstance(post, dict) and post.get("shipped_no_content") is not None:
        wasted = int(post["shipped_no_content"]) * float(SAMPLE_COST)
        rows.append((wasted, "Seeding leak (ship → no content)",
                     f'{post["shipped_no_content"]} of {post.get("shipped", "?")} shipped never posted '
                     f'({pct(post.get("wasted_spend_rate"))})',
                     "Gate low-post-rate creators; require a post commitment before the next ship."))

    try:
        camps = pd.read_csv(CONTRACT["campaigns"])
        for _, c in camps.iterrows():
            r, be = _f(c.get("roas")), _f(c.get("breakeven_roas"))
            spend = _f(c.get("spend_30d"))
            if r is not None and be is not None and r < be and spend:
                at_risk = round(spend * max(0.0, (be - r) / be))
                rows.append((at_risk, f'Campaign below breakeven — {c.get("campaign_name")}',
                             f'ROAS {num(r,2)}× vs breakeven {num(be,2)}× on {money(spend)}/mo spend',
                             f'Raise the target to ≥ {num(be,2)}× or pause; it loses money at the current goal.'))
    except Exception:
        pass

    het = d.get("hetero", {})
    if isinstance(het, dict):
        for s in het.get("segments", []):
            if _f(s.get("vs_overall")) is not None and s["vs_overall"] < 0:
                rows.append((None, f'Weak segment — {s.get("segment")}',
                             f'CATE {s.get("mean_lift")} vs portfolio {het.get("overall_mean_lift")} '
                             f'({s.get("vs_overall")} lift)',
                             "De-prioritize this segment in the next sampling cycle."))
                break

    drift = d.get("drift", {})
    if isinstance(drift, dict):
        for flag in (drift.get("flags") or []):
            rows.append((None, "Model drift flag", esc(flag),
                         "Re-baseline after the known data change; investigate if unexplained."))

    if not rows:
        return section("Problem areas", '<p class="unavail">no ranked problems surfaced</p>', idx="3")
    quantified = sorted([r for r in rows if r[0] is not None], key=lambda x: -x[0])
    unq = [r for r in rows if r[0] is None]
    trs = []
    for dollars, area, ev, fix in quantified + unq:
        trs.append([esc(area), esc(ev), f'<b>{money(dollars)}</b>' if dollars is not None else "—", esc(fix)])
    body = table(["Area", "Evidence", "Est. $ at stake", "Recommended fix"], trs, right={2})
    read = (f"The biggest fixable leak is {quantified[0][1].lower()} at ~{money(quantified[0][0])}."
            if quantified else "The surfaced problems are real but not dollar-quantifiable at this scale.")
    return section("Problem areas — ranked by dollars at stake", body,
                   sub="Estimates use measured unit costs only (e.g. wasted samples × $%.0f cost, spend below "
                       "breakeven). Real-but-unquantified problems sort last with “—”." % SAMPLE_COST,
                   idx="3", tag="ACT", read=read)


def _action_queue(d):
    dq = d.get("decisions", {})
    nl = note_row(dq, "queue")
    if nl:
        return section("Action queue", nl, idx="4")
    rows = ""
    q = dq.get("queue", [])
    for a in q:
        why = list(a.get("why", []))
        instr = ""
        if why and str(why[-1]).lstrip().startswith("→"):
            instr = f'<div class="instr">{esc(why[-1])}</div>'   # the exact change comes FIRST
            why = why[:-1]
        lever = {"campaign": "GMV Max", "spark": "Spark", "sample": "Sample"}.get(a.get("type"), a.get("type"))
        tgt = at_or_name(a)
        title = f'<span class="q-ctx">{esc(a.get("title", ""))}</span>' if a.get("title") else ""
        # evidence in <details open> — MUST be open, closed <details> vanish in print
        evidence = ""
        if why:
            bullets = "".join(f"<li>{esc(w)}</li>" for w in why)
            evidence = (f'<details open class="q-ev"><summary>why</summary>'
                        f'<ul class="q-why">{bullets}</ul></details>')
        rows += (f'<div class="qrow"><div class="q-head">{chip(a.get("action"), verdict_status(a.get("action")))}'
                 f'<span class="q-target">{tgt}</span> {title}'
                 f'<span class="q-lever">{esc(lever)}</span></div>'
                 f'{instr}{evidence}</div>')
    with_instr = sum(1 for a in q if a.get("why") and str(a["why"][-1]).lstrip().startswith("→"))
    read = f"{len(q)} actions queued; {with_instr} come with an exact change to make."
    return section("Action queue — full detail", f'<div class="queue">{rows}</div>',
                   sub=esc(dq.get("note", "")) + f' · generated {esc(dq.get("generated", ""))}',
                   idx="4", tag="ACT", read=read)


def _voc_week(d):
    iw = d.get("intent_week", {})
    parts = []
    nl = note_row(iw, "themes")
    if nl:
        parts.append(nl)
    else:
        cards = ""
        for t in iw.get("themes", []):
            cards += (f'<div class="voc-card"><div class="voc-theme">{esc(t["theme"])}</div>'
                      f'<div class="voc-count">{t["n"]} comments · {pct(t["share"])} of the week</div>'
                      f'<div class="voc-quote">“{esc(t["quote"])}”</div>'
                      f'<div class="voc-attr">{esc(at(t["handle"]))} · {t["likes"]} likes</div></div>')
        parts.append(f'<h3>Themes of the week (last {iw.get("window_days", 10)} days · '
                     f'{iw.get("total", 0)} comments)</h3><div class="voc-cards">{cards}</div>')

    vc = d.get("voc_campaigns", [])
    if isinstance(vc, list) and vc:
        rows = ""
        for c in vc:
            quotes = "<br/>".join(f'“{esc(q["text"])}” — {esc(at(q["handle"]))}' for q in c.get("quotes", []))
            rows += (f'<div class="qrow"><div class="q-head">'
                     f'{chip(c.get("verdict") or "—", verdict_status(c.get("verdict")))}'
                     f'<span class="q-target">{esc(c["campaign"])}</span>'
                     f'<span class="q-lever">{c["n"]} comments</span></div>'
                     f'<div class="q-ctx">{esc(" · ".join(c.get("themes", [])))}</div>'
                     f'<div class="voc-quote">{quotes}</div></div>')
        parts.append('<h3>By campaign — what the audience is saying under each ad</h3>'
                     f'<div class="queue">{rows}</div>'
                     '<p class="foot">Read it against the verdict: price pushback on a TUNE row → discount test; '
                     'buy-intent on a CUT row → the problem is economics, not demand.</p>')
    read = "No comments landed in the window."
    if isinstance(iw, dict) and iw.get("themes"):
        t0 = iw["themes"][0]
        read = f"“{t0['theme']}” leads the week at {pct(t0['share'])} of {iw.get('total', 0)} comments."
    return section("Voice of the customer — this week", "".join(parts),
                   sub="Weekly comment themes with real (synthetic) quotes, then joined to each live campaign.",
                   idx="5", tag="CONTEXT", read=read)


def _trend_desk(d):
    tr = d.get("trends")
    if not isinstance(tr, list) or not tr:
        return section("Trend desk", '<p class="unavail">unavailable — no monthly series</p>', idx="6")
    months = [r["month"] for r in tr]
    LAGGED = {"gmv": "Matured GMV", "profit": "Incremental profit", "win_rate": "Win rate"}
    metrics = [("samples", "Samples shipped", False, lambda v: num(v, 0)),
               ("gmv", "Matured GMV", True, money),
               ("profit", "Incremental profit", True, money),
               ("win_rate", "Win rate", True, lambda v: pct(v))]
    any_trim = False
    rows = []
    for key, label, lagged, fmt in metrics:
        series = [r.get(key) for r in tr]
        matured = [v for v in series if v is not None]
        trimmed = len(series) - len(matured) if lagged else 0
        any_trim = any_trim or (trimmed > 0)
        spk = spark_svg(matured if lagged else series)
        last3 = " · ".join(fmt(v) for v in (matured if lagged else series)[-3:])
        m = mom((matured if lagged else series)[-1] if (matured if lagged else series) else None,
                (matured if lagged else series)[-2] if len(matured if lagged else series) > 1 else None)
        traj = trajectory(matured if lagged else series)
        dagger = " †" if trimmed else ""
        tcol = {"improving": STATUS["good"], "deteriorating": STATUS["critical"]}.get(traj, STATUS["neutral"])
        rows.append([esc(label) + dagger, spk, last3, m, f'<span style="color:{tcol}">{esc(traj)}</span>'])
    body = table(["Metric", "Trajectory", "Last 3", "MoM", ""], rows, right={3})
    foot = ""
    if any_trim:
        foot = ('<p class="foot">† Lagged outcome metrics: the last 2 months are immature (outcomes take '
                '~40 days to attribute), so they are trimmed from the trend to avoid a false $0. '
                'Volume metrics (samples) are shown in full.</p>')
    prof = [r.get("profit") for r in tr if r.get("profit") is not None]
    read = f"Matured profit is {trajectory(prof)} over the window; the last 2 months are still maturing."
    return section("Trend desk", body + foot,
                   sub="Metric × month, with each trajectory classified by least-squares slope. Months: "
                       + esc(" · ".join(months)), idx="6", tag="CONTEXT", read=read)


def _forward(d):
    prize = d.get("prize", {})
    tiles = []
    if isinstance(prize, dict) and prize.get("expected_profit_per_sample") is not None:
        tiles.append(tile("Expected profit / sample", money(prize["expected_profit_per_sample"]),
                          sub=f'over {prize.get("samples_per_month", "?")} samples/mo'))
        tiles.append(tile("Annualized incremental profit", money(prize.get("annual_incremental_profit")),
                          sub="expected value at current pace", accent=True))
        tiles.append(tile("Annual sample spend", money(prize.get("annual_sample_spend")),
                          sub=esc(prize.get("caveat", ""))[:80]))
    forecast = '<div class="tiles">' + "".join(tiles) + "</div>" if tiles else ""

    dq = d.get("decisions", {})
    queue = dq.get("queue", []) if isinstance(dq, dict) else []
    acts = []
    for a in queue[:8]:
        instr = next((w for w in reversed(a.get("why", [])) if str(w).lstrip().startswith("→")), None)
        if instr:
            acts.append(f'<li>{chip(a.get("action"), verdict_status(a.get("action")))} '
                        f'{at_or_name(a)} — {esc(instr)}</li>')
    actby = f'<h3>Act by end of week</h3><ul class="acts">{"".join(acts)}</ul>' if acts else ""

    watch = []
    try:
        camps = pd.read_csv(CONTRACT["campaigns"])
        for _, c in camps.iterrows():
            r, be = _f(c.get("roas")), _f(c.get("breakeven_roas"))
            if r is not None and be is not None and abs(r - be) / be < 0.12:
                watch.append(f'<li>{esc(c.get("campaign_name"))}: ROAS {num(r,2)}× hovering at breakeven '
                             f'{num(be,2)}× — one bad week flips the verdict.</li>')
    except Exception:
        pass
    watchlist = f'<h3>Verdict-flip watchlist</h3><ul class="acts">{"".join(watch[:5])}</ul>' if watch else ""

    cal = ('<h3>The machine\'s own calendar</h3><ul class="acts">'
           '<li>Nightly: corpora re-ingested, snapshots recomputed, freshness stamp refreshed.</li>'
           '<li>Weekly: roster re-ranked from new outcomes, model refit, holdout ledger advanced.</li>'
           '<li>Continuous: drift monitor watches input PSI + ranker skill vs the saved baseline.</li>'
           '<li>This report regenerates from the latest snapshot every time it is opened.</li></ul>')
    ann = prize.get("annual_incremental_profit") if isinstance(prize, dict) else None
    read = (f"At the current pace the program projects ~{money(ann)}/yr in incremental profit."
            if ann is not None else "Forecasts, the act-by list, and the system's own refresh cadence.")
    return section("What's next — forward 30 days", forecast + actby + watchlist + cal,
                   sub="Forecasts, the act-by list, verdicts at risk of flipping, and the system's own refresh cadence.",
                   idx="7", tag="ACT", read=read)


def _deep(d):
    parts = []
    al = d.get("allocate", {})
    nl = note_row(al, "allocated")
    if nl:
        parts.append("<h3>Budget allocation</h3>" + nl)
    else:
        paid = al.get("paid_gmv_max", {})
        samp = al.get("sampling", {})
        pcamps = "".join(f'<li>{esc(c.get("campaign"))}: {money(c.get("$"))} '
                         f'({num(c.get("return_per_dollar"),2)}× per $1)</li>' for c in paid.get("campaigns", []))
        tiers = "".join(f'<li>ranks {esc(t.get("ranks"))}: {t.get("n")} samples · '
                        f'{money(t.get("profit_per_sample"))}/sample</li>' for t in samp.get("tiers", []))
        parts.append(
            f'<h3>Budget allocation — {money(al.get("budget"))}</h3>'
            f'<p>{money(al.get("allocated"))} allocated · '
            f'<b>{money(al.get("unspent"))} unspent</b> (no profitable next dollar). '
            f'Paid {pct(al.get("split", {}).get("paid_pct"))} / Sampling {pct(al.get("split", {}).get("sampling_pct"))}. '
            f'Expected incremental profit {money(al.get("expected_incremental_profit"))}.</p>'
            f'<div class="cols"><div><b>Paid GMV Max</b><ul class="acts">{pcamps or "<li>none profitable</li>"}</ul></div>'
            f'<div><b>Sampling tiers</b><ul class="acts">{tiers or "<li>—</li>"}</ul></div></div>'
            f'<p class="foot">{esc(al.get("assumptions", {}).get("caveat", ""))}</p>')

    sens = d.get("sensitivity", {})
    if isinstance(sens, dict) and sens.get("rows"):
        cost_keys = [k for k in sens["rows"][0].keys() if k.startswith("cost_")]
        headers = ["Net margin"] + [f'${k.split("_")[1]} cost' for k in cost_keys]
        trs = [[pct(r.get("net_margin")) ] + [num(r.get(k), 2) + "×" for k in cost_keys] for r in sens["rows"]]
        parts.append("<h3>ROI sensitivity — margin × sample cost</h3>"
                     + table(headers, trs, right=set(range(1, len(headers))))
                     + f'<p class="foot">{esc(sens.get("note", ""))}</p>')

    sp = d.get("spark", {})
    if isinstance(sp, dict) and sp.get("timing"):
        trs = [[esc(t.get("age_band")), f'<b>{num(t.get("avg_roas"),2)}×</b>', num(t.get("n"), 0)] for t in sp["timing"]]
        parts.append("<h3>Spark timing — ROAS by video age at first spark</h3>"
                     + table(["Age at spark", "Avg ROAS", "Videos"], trs, right={1, 2})
                     + f'<p class="foot">{esc(sp.get("note", ""))}</p>')

    ltv, ret = d.get("ltv", {}), d.get("retention", {})
    if isinstance(ltv, dict) and ltv.get("median_ltv_net_contribution") is not None:
        curve = ret.get("curve", []) if isinstance(ret, dict) else []
        cbars = "".join(bar(p.get("retained"), f'M{p.get("month")}: {pct(p.get("retained"))}') for p in curve)
        parts.append("<h3>Program P&amp;L — lifetime value &amp; retention</h3>"
                     f'<p>Median LTV (net contribution) {money(ltv.get("median_ltv_net_contribution"))} · '
                     f'repeat rate {pct(ltv.get("repeat_rate"))} · one-and-done {pct(ltv.get("one_and_done_rate"))}.</p>'
                     f'<div class="bars">{cbars}</div>')

    rec = d.get("recommend", {})
    if isinstance(rec, dict) and rec.get("candidates"):
        trs = [[f'#{c.get("rank")}', at(c.get("handle")), esc(c.get("tier")),
                (f"{c.get('followers'):,}" if c.get("followers") else "—"),
                "cold-start" if c.get("cold_start") else esc(str(c.get("watchouts", ""))[:60] or "—")]
               for c in rec["candidates"][:10]]
        exc = rec.get("excluded", {})
        parts.append("<h3>Next picks — with guardrails</h3>"
                     + table(["Rank", "Creator", "Tier", "Followers", "Watch-outs"], trs, right={3})
                     + f'<p class="foot">Excluded to protect the experiment: {exc.get("seeded", 0)} already-seeded, '
                     f'{exc.get("control", 0)} matched controls. Ordinal ranks only.</p>')

    voc = d.get("voc", {})
    if isinstance(voc, dict) and voc.get("competitor_board"):
        mix = " · ".join(f"{esc(k)} {pct(v)}" for k, v in (voc.get("category_mix", {}) or {}).items())
        board = " · ".join(f'{esc(c.get("competitor"))} ({c.get("mentions")})' for c in voc["competitor_board"])
        parts.append("<h3>Corpus-wide voice of customer</h3>"
                     f'<p>{voc.get("total", 0):,} comments. Category mix: {mix}.<br/>'
                     f'<b>Competitor board</b> (synthetic brands): {board}.</p>')
    return section("Deep dives", "".join(parts),
                   sub="Budget optimization, sensitivity, timing, program economics, next picks, and the full VoC.",
                   idx="8", tag="CONTEXT",
                   read="The supporting analysis behind the calls above — read it when you want the full picture.")


def _appendix(d):
    parts = ['<p class="foot">The ranker is a <b>deterministic-ordinal</b> model — it emits ranks, not '
             'dollar predictions, so there are no learned coefficients to print. These are the diagnostics '
             'that prove it separates winners: out-of-sample skill, calibration by rank, a controlled lift '
             'test, and drift.</p>']

    rec = d.get("recommender", {})
    if isinstance(rec, dict) and rec.get("precision_at_k"):
        trs = [[f'@{p.get("k")}', pct(p.get("precision")), num(p.get("median_lift"), 0)] for p in rec["precision_at_k"]]
        parts.append(f'<h3>Ranker skill</h3><p>Rank-IC {num(rec.get("rank_ic"),3)} '
                     f'(Spearman rank↔realized lift) vs base win-rate {pct(rec.get("base_win_rate"))}.</p>'
                     + table(["Precision@K", "Hit rate", "Median lift"], trs, right={1, 2}))
        cal = rec.get("calibration", {})
        if isinstance(cal, dict) and cal.get("bins"):
            cbars = "".join(bar((b.get("mean_lift") or 0) / max(1, (cal["bins"][0].get("mean_lift") or 1)),
                                 f'ranks {b.get("rank_range")}: lift {num(b.get("mean_lift"),0)}') for b in cal["bins"])
            parts.append(f'<h4>Calibration by rank quintile (monotonic: {cal.get("monotonic")})</h4>'
                         f'<div class="bars">{cbars}</div>')

    ho = d.get("holdout", {})
    qe = ho.get("quasi_experiment", {}) if isinstance(ho, dict) else {}
    if isinstance(qe, dict) and qe.get("lift") is not None:
        parts.append('<h3>Controlled lift test</h3>'
                     f'<p>Engine picks vs matched controls: <b>{money(qe.get("lift"))}</b>/sample '
                     f'(95% CI {money(qe.get("ci_low"))}–{money(qe.get("ci_high"))}, p={num(qe.get("p_value"),3)}, '
                     f'n={qe.get("n_treatment")} vs {qe.get("n_control")}). {esc(qe.get("design", ""))}</p>')

    tl = d.get("theme_lift", {})
    vl = tl.get("video_level", {}) if isinstance(tl, dict) else {}
    if isinstance(vl, dict) and vl.get("associations"):
        trs = [[esc(_CAT_LABEL.get(a.get("theme"), a.get("theme"))), num(a.get("r"), 3),
                num(a.get("p"), 3), "✓" if a.get("significant") else ""] for a in vl["associations"]]
        parts.append("<h3>Comment-theme → conversion (Bonferroni)</h3>"
                     + table(["Theme", "r", "p", "sig"], trs, right={1, 2, 3})
                     + f'<p class="foot">{esc(vl.get("note", ""))}</p>')

    drift = d.get("drift", {})
    if isinstance(drift, dict) and drift.get("psi_by_feature"):
        trs = [[esc(k), num(v, 3), "stable" if v < 0.1 else ("moderate" if v < 0.25 else "shifted")]
               for k, v in drift["psi_by_feature"].items()]
        flags = drift.get("flags") or []
        parts.append("<h3>Model-drift monitor</h3>" + table(["Feature", "PSI", "Status"], trs, right={1})
                     + (f'<p class="foot">Flags: {esc("; ".join(flags))}</p>' if flags else
                        '<p class="foot">No drift flags.</p>'))
    elif isinstance(drift, dict) and drift.get("status") == "baseline_written":
        parts.append('<h3>Model-drift monitor</h3><p class="foot">Baseline written this run; PSI compares on the '
                     'next cycle.</p>')
    ric = rec.get("rank_ic") if isinstance(rec, dict) else None
    read = (f"The ranker separates winners out-of-sample (rank-IC {num(ric, 3)}) — the numbers behind the trust."
            if ric is not None else "Diagnostics behind the ranker, for readers who want to check the math.")
    return section("Technical appendix — model diagnostics", "".join(parts),
                   sub="Proof the system learns, for readers who want to check the math.",
                   idx="9", tag="TECHNICAL", read=read)


def _methodology():
    bullets = [
        "<b>Lift is causal, not before/after.</b> Every incremental-profit number compares seeded creators "
        "to matched controls (similar rank, niche, follower band), so it isn't just growth the creator would "
        "have had anyway.",
        "<b>Ranks order; dollars decide.</b> The ranker is ordinal — it says who's more promising, not how much "
        "they'll earn. Budget and go/no-go come from the economics, not the rank number.",
        "<b>The model retrains behind a gate.</b> A weekly refit only ships if it still separates winners "
        "out-of-sample; the drift monitor can hold a release.",
        "<b>Exploration is deliberate.</b> Some samples go to less-certain creators on purpose (Thompson-style "
        "draws) so the system keeps learning instead of only exploiting what it already knows.",
        "<b>Not all VoC claims are equal.</b> “Validated” themes are correlated with conversion at significance; "
        "“directional” ones are there to brief humans, not to move the ranking.",
    ]
    body = '<ol class="method">' + "".join(f"<li>{b}</li>" for b in bullets) + "</ol>"
    return section("Methodology", body,
                   sub="Five plain-English notes on the measurement design.", idx="11", tag="TECHNICAL",
                   read="How the numbers are measured — read this once and you can trust the rest.")


_TOC_ROWS = [
    ("1", "Scoreboard", "CONTEXT", "where the numbers stand + which way they're moving"),
    ("2", "Three moves this week", "ACT", "the three highest-value things to do now"),
    ("3", "Problem areas", "ACT", "what's leaking money, ranked by dollars"),
    ("4", "Action queue", "ACT", "every campaign / spark / sample call with the exact change"),
    ("5", "Voice of the customer", "CONTEXT", "what buyers are saying this week, per campaign"),
    ("6", "Trend desk", "CONTEXT", "each metric's trajectory over recent months"),
    ("7", "What's next", "ACT", "forecasts, act-by list, verdicts at risk of flipping"),
    ("8", "Deep dives", "CONTEXT", "the supporting analysis behind the calls above"),
    ("9", "Technical appendix", "TECHNICAL", "proof the ranker works — skip freely"),
    ("10", "Glossary", "TECHNICAL", "every term in plain words"),
    ("11", "Methodology", "TECHNICAL", "how the numbers are measured"),
]


def _toc():
    rows = "".join(
        f'<div class="toc-row"><span class="toc-n">§{n}</span><span class="toc-t">{esc(t)}</span>'
        f'<span class="s-tag t-{tag.lower()}">{esc(tag)}</span><span class="toc-w">{esc(w)}</span></div>'
        for n, t, tag, w in _TOC_ROWS)
    route = ('Your team acts on <b class="t-act">ACT</b>; <b class="t-context">CONTEXT</b> is the why; '
             '<b class="t-technical">TECHNICAL</b> exists so you can trust the rest — skip it freely.')
    return section("How to use this report", f'<div class="toc">{rows}</div><p class="toc-route">{route}</p>',
                   page_break=False)


_GLOSSARY = [
    ("ROAS", "Return on ad spend — dollars back per $1 spent on a campaign."),
    ("Breakeven ROAS", "The ROAS a campaign must clear to cover product + fees; below it, the campaign "
                       "loses money even when it looks like it's 'working'."),
    ("Incremental lift", "Extra sales caused by sampling a creator, above what they'd have sold anyway."),
    ("Matched control", "A similar un-sampled creator used as the comparison, so lift is causal, not just growth."),
    ("Holdout", "A controlled test — engine picks vs. status quo — reported with a confidence interval."),
    ("Rank-IC", "How well the ranking order matches realized results (Spearman). Negative here = winners on top."),
    ("Precision@K", "Of the top K picks, the share that turned out to be winners."),
    ("CATE", "Which creator segments respond most to sampling (conditional average treatment effect)."),
    ("PSI / drift", "A stability score on model inputs; high means the data shifted and the model may need a refit."),
    ("Spark", "Putting ad spend behind an organic video that's already taking off."),
    ("GMV Max", "TikTok's auto-optimized shopping-campaign type."),
    ("Post rate", "Share of shipped samples that actually became content."),
    ("Maturation lag", "Sales take ~40 days to attribute, so the newest months look low until they mature."),
]


def _glossary():
    items = "".join(f'<div class="gl"><b>{esc(t)}</b> {esc(d)}</div>' for t, d in _GLOSSARY)
    return section("Glossary", f'<div class="glossary">{items}</div>',
                   sub="One vocabulary — the same terms appear on the dashboard.",
                   idx="10", tag="TECHNICAL", read="Every term used above, in plain words.")


# ── CSS (print-first, light) ─────────────────────────────────────────────────────────────────
_CSS = """
:root{--ink:#0b0b0b;--sec:#52514e;--muted:#898781;--line:#e1e0d9;--blue:#2a78d6;--paper:#fff;}
*{box-sizing:border-box;-webkit-print-color-adjust:exact;print-color-adjust:exact;}
body{background:var(--paper);color:var(--ink);font:10.5px/1.5 -apple-system,Segoe UI,Roboto,system-ui,sans-serif;
     max-width:780px;margin:0 auto;padding:22px 20px 60px;font-variant-numeric:tabular-nums;}
h1{font-size:21px;margin:2px 0 4px;letter-spacing:-.01em;}
h2{font-size:14.5px;margin:0 0 3px;letter-spacing:-.005em;}
h3{font-size:11.5px;margin:14px 0 5px;}
h4{font-size:10.5px;margin:9px 0 4px;color:var(--sec);}
p{margin:5px 0;}
.rpt-head{border-bottom:2px solid var(--ink);padding-bottom:11px;margin-bottom:16px;}
.kicker{color:var(--blue);font-size:9px;letter-spacing:.16em;text-transform:uppercase;font-weight:700;}
.meta{color:var(--muted);font-size:9.5px;margin-top:3px;}
.capstrip{color:var(--sec);font-size:9.8px;margin-top:8px;border-left:2px solid var(--blue);padding-left:9px;}
.sec{margin:20px 0;position:relative;}
.sec.pb{page-break-before:always;}
h2,h3,h4{page-break-after:avoid;}
.s-num{position:absolute;left:-20px;top:1px;color:var(--line);font-size:12px;font-weight:700;}
.s-sub{color:var(--muted);font-size:9.3px;margin-bottom:9px;max-width:640px;}
.tiles{display:grid;grid-template-columns:repeat(4,1fr);gap:9px;margin:8px 0;}
.tile{border:1px solid var(--line);border-radius:6px;padding:8px 10px;page-break-inside:avoid;}
.t-label{color:var(--muted);font-size:8.3px;letter-spacing:.05em;text-transform:uppercase;}
.t-value{font-size:16px;font-weight:650;margin:3px 0 1px;letter-spacing:-.01em;}
.t-mark{font-size:9px;font-weight:400;white-space:nowrap;}
.t-sub{color:var(--muted);font-size:8.3px;line-height:1.3;}
.spark{vertical-align:middle;}
.delta{font-size:9px;font-weight:700;margin-left:3px;}
.moves{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-top:8px;}
.move{border:1px solid var(--line);border-radius:6px;padding:10px;page-break-inside:avoid;}
.move-tag{font-size:9px;font-weight:800;letter-spacing:.1em;}
.move-target{font-size:12.5px;font-weight:700;margin:3px 0;}
.move-meta{color:var(--sec);font-size:9.2px;margin-bottom:6px;}
.instr{border-left:2px solid var(--blue);background:#f4f8fd;padding:5px 8px;font-weight:600;font-size:9.6px;
       border-radius:0 4px 4px 0;margin-top:5px;}
table{width:100%;border-collapse:collapse;margin:6px 0;font-size:9.5px;}
th{color:var(--muted);font-weight:600;text-align:left;border-bottom:1px solid var(--ink);padding:4px 7px 4px 0;
   font-size:8.6px;letter-spacing:.03em;text-transform:uppercase;}
td{border-bottom:1px solid var(--line);padding:4px 7px 4px 0;vertical-align:top;}
th.r,td.r{text-align:right;padding-right:0;}
tr{page-break-inside:avoid;}
.chip{display:inline-block;border:1px solid;border-radius:4px;padding:0 5px;font-size:8.4px;font-weight:700;
      letter-spacing:.04em;margin-right:5px;vertical-align:middle;}
.queue{margin-top:6px;}
.qrow{border:1px solid var(--line);border-radius:6px;padding:8px 10px;margin-bottom:7px;page-break-inside:avoid;}
.q-head{display:flex;align-items:center;gap:7px;}
.q-target{font-weight:700;font-size:11px;color:var(--ink);}
.q-lever{color:var(--muted);font-size:8.5px;margin-left:auto;text-transform:uppercase;letter-spacing:.05em;}
.q-ctx{color:var(--sec);font-size:9px;margin:3px 0;}
.q-why{margin:4px 0 0;padding-left:15px;color:var(--sec);}
.q-why li{margin:1px 0;}
.voc-cards{display:grid;grid-template-columns:repeat(2,1fr);gap:8px;}
.voc-card{border:1px solid var(--line);border-radius:6px;padding:9px;page-break-inside:avoid;}
.voc-theme{font-weight:700;font-size:10.5px;}
.voc-count{color:var(--muted);font-size:8.6px;margin:1px 0 5px;}
.voc-quote{font-style:italic;color:var(--sec);font-size:9.4px;}
.voc-attr{color:var(--muted);font-size:8.4px;margin-top:4px;}
.acts{margin:4px 0;padding-left:16px;}
.acts li{margin:3px 0;}
.cols{display:grid;grid-template-columns:1fr 1fr;gap:14px;}
.bars{margin:6px 0;}
.bar{position:relative;height:14px;background:#f3f2ee;border-radius:3px;margin:3px 0;overflow:hidden;}
.bar-fill{position:absolute;top:0;bottom:0;left:0;border-radius:3px;opacity:.85;}
.bar.signed .bar-mid{position:absolute;left:50%;top:0;bottom:0;width:1px;background:var(--muted);}
.bar-label{position:absolute;left:6px;top:0;line-height:14px;font-size:8.4px;color:var(--ink);white-space:nowrap;}
.method{margin:5px 0;padding-left:18px;}
.method li{margin:5px 0;}
.foot{color:var(--muted);font-size:8.8px;margin-top:6px;}
.unavail{color:var(--muted);font-style:italic;font-size:9.3px;}
.s-head{display:flex;align-items:center;gap:9px;}
.t-act{color:#b8641e;} .t-context{color:#2a78d6;} .t-technical{color:#8a8880;}
.s-tag{font-size:7.4px;font-weight:800;letter-spacing:.09em;padding:1px 6px;border-radius:999px;
  border:1px solid currentColor;background:color-mix(in srgb,currentColor 12%,transparent);
  text-transform:uppercase;white-space:nowrap;}
.s-read{font-size:9.6px;margin:5px 0 9px;padding:5px 9px;background:#f6f5f1;border-radius:5px;line-height:1.45;}
.s-read .rl{font-weight:800;letter-spacing:.06em;font-size:7.8px;color:var(--muted);margin-right:7px;}
.toc-row{display:grid;grid-template-columns:30px 148px 62px 1fr;gap:8px;align-items:center;
  padding:3px 0;border-bottom:1px solid var(--line);font-size:9.3px;}
.toc-n{color:var(--muted);font-weight:700;} .toc-t{font-weight:600;} .toc-w{color:var(--sec);}
.toc-route{font-size:9.3px;margin-top:9px;color:var(--sec);}
.glossary{column-count:2;column-gap:22px;margin-top:4px;}
.gl{break-inside:avoid;margin:0 0 7px;font-size:9.3px;line-height:1.4;}
.gl b{color:var(--ink);}
.q-ev{margin-top:5px;}
.q-ev summary{font-size:8.2px;color:var(--muted);text-transform:uppercase;letter-spacing:.06em;cursor:default;}
.q-ev .q-why{margin-top:3px;}
"""


def build_report_html(budget=50000):
    d = build_report_data(budget)
    sections = [
        _header(d), _toc(), _scoreboard(d), _three_moves(d), _problems(d), _action_queue(d),
        _voc_week(d), _trend_desk(d), _forward(d), _deep(d), _appendix(d), _glossary(), _methodology(),
    ]
    body = "".join(sections)
    return (f'<!doctype html><html><head><meta charset="utf-8"/>'
            f'<title>Agency report — {AS_OF}</title><style>{_CSS}</style></head>'
            f'<body>{body}<footer class="foot" style="margin-top:24px;border-top:1px solid var(--line);'
            f'padding-top:8px">100% synthetic data (scripts/gen_data.py). Competitor names, handles, and figures '
            f'are fabricated. Framework: docs/REPORT-FRAMEWORK.md.</footer></body></html>')


# ── PDF via installed Chrome/Chromium ────────────────────────────────────────────────────────
def chrome_path():
    env = os.getenv("CHROME_PATH")
    if env and Path(env).exists():
        return env
    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "chrome", "msedge"):
        p = shutil.which(name)
        if p:
            return p
    candidates = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        "/usr/bin/chromium", "/usr/bin/chromium-browser", "/usr/bin/google-chrome",
    ]
    for c in candidates:
        if c and Path(c).exists():
            return c
    return None


def build_report_pdf(budget=50000) -> Path:
    exe = chrome_path()
    if not exe:
        raise RuntimeError("no Chrome/Chromium found for PDF rendering — open /report and print from the browser")
    html_doc = build_report_html(budget)
    tmp = Path(tempfile.mkdtemp(prefix="report_"))
    src, out = tmp / "report.html", tmp / "report.pdf"
    src.write_text(html_doc, encoding="utf-8")
    cmd = [exe, "--headless=new", "--disable-gpu", "--no-first-run", "--no-sandbox",
           f"--user-data-dir={tmp / 'chrome-tmp'}",   # throwaway profile — never a shared/real one
           "--no-pdf-header-footer", f"--print-to-pdf={out}", src.as_uri()]
    subprocess.run(cmd, check=True, capture_output=True, timeout=120)
    if not out.exists():
        raise RuntimeError("Chrome ran but produced no PDF")
    return out


# 15-min cache + single-flight lock: a report build is ~30-45s (Chrome + data assembly), and users
# double-click the button. The lock makes impatient re-clicks share one build instead of spawning many.
_PDF_CACHE, _PDF_LOCK, _PDF_TTL = {}, threading.Lock(), 15 * 60


def build_report_pdf_cached(budget=50000) -> Path:
    hit = _PDF_CACHE.get(budget)
    if hit and time.monotonic() - hit[0] < _PDF_TTL and hit[1].exists():
        return hit[1]
    with _PDF_LOCK:
        hit = _PDF_CACHE.get(budget)              # re-check inside the lock (another thread may have built)
        if hit and time.monotonic() - hit[0] < _PDF_TTL and hit[1].exists():
            return hit[1]
        p = build_report_pdf(budget)
        _PDF_CACHE[budget] = (time.monotonic(), p)
        return p
