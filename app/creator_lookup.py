"""Creator lookup — the reverse of the recommendation flow: the engine's dossier on ONE creator.

Managers get the reverse question mid-call ("what does the engine think of @x?") about a creator who
is usually invisible (not a top pick, not in flight). Three honest tiers:
  1. ranked shortlist  → the IDENTICAL rank / outlook / evidence a recommended pick would show (reuses
     the recommend card).
  2. in roster, not ranked → real roster metrics + a computed playbook outlook, framed honestly as
     "in roster — not in the ranked shortlist" (seeded / matched-control / just not scored).
  3. history-only / unknown → past measured lift + content record + recent shipments, or an honest
     "brand-new or the handle is spelled differently".

Handle is validated before use (reject, don't sanitize), and lookups are cached per normalized handle.
Synthetic data only.
"""
import re
from functools import lru_cache

import pandas as pd

from app.config import CONTRACT

_HANDLE_RE = re.compile(r"^[a-z0-9._]{2,40}$")


def _at(h):
    return "@" + str(h).lstrip("@")


@lru_cache(maxsize=1)
def _ranked():
    """The model's ranked shortlist as {normalized_handle: card}. recommend() already excludes
    seeded + matched controls, so absence here is meaningful (that's tier 2)."""
    from app.recommend import recommend
    cands = recommend(n=100000).get("candidates", [])
    return {str(c.get("handle", "")).lstrip("@").lower(): c for c in cands}


@lru_cache(maxsize=8)   # one entry per table (roster/creators/…) — NOT 1, or they evict each other
def _by_handle(key):
    df = pd.read_csv(CONTRACT[key])
    return {str(h).lstrip("@").lower(): r for h, r in zip(df["handle"], df.to_dict("records"))}


@lru_cache(maxsize=1)
def _sreq():
    return pd.read_csv(CONTRACT["sample_requests"])


@lru_cache(maxsize=1)
def _comments():
    return pd.read_csv(CONTRACT["comments"])


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def lookup(handle):
    """Public entry: normalize + validate, then hit the cached core. `@Creator` and `creator` share
    a cache entry."""
    h = str(handle or "").strip().lstrip("@").lower()
    if not _HANDLE_RE.match(h):
        return {"found": False, "handle": handle,
                "note": "invalid handle — use letters, digits, dot or underscore (2–40 chars)."}
    return _lookup(h)


@lru_cache(maxsize=256)
def _lookup(h):
    out = {"handle": _at(h), "found": False, "tier": "unknown", "chips": [], "metrics": [],
           "evidence": [], "watchouts": [], "outlook": None, "note": ""}

    def metric(label, value, hint=""):
        out["metrics"].append({"label": label, "value": ("" if value is None else str(value)), "hint": hint})

    # ── shared history (all tiers) ───────────────────────────────────────────────────────────
    sr = _sreq()
    srow = sr[sr["creator_handle"].astype(str).str.lstrip("@").str.lower() == h]
    posted = int((srow["status"] == "Completed").sum())
    shipped = int(len(srow))
    recent = []
    if shipped:
        for _, r in srow.sort_values("shipped_time", ascending=False).head(5).iterrows():
            recent.append({"product": str(r.get("product_id", "")), "status": str(r.get("status", "")),
                           "date": str(r.get("shipped_time", ""))[:10]})

    odf = pd.read_csv(CONTRACT["outcomes"])
    orow = odf[odf["handle"].astype(str).str.lower() == h]
    past_lift = None
    if len(orow):
        col = "did_lift_refadj" if "did_lift_refadj" in orow.columns else "did_lift"
        past_lift = round(float(orow.iloc[0][col]))

    cm = _comments()
    crow = cm[cm["handle"].astype(str).str.lower() == h]
    intent_n = int(crow["category"].isin(["purchase", "confirmed_purchase"]).sum()) if len(crow) else 0
    comment_n = int(len(crow))

    card = _ranked().get(h)
    ros = _by_handle("roster").get(h)
    cre = _by_handle("creators").get(h)

    # ── tier 1: ranked shortlist ─────────────────────────────────────────────────────────────
    if card:
        out["found"], out["tier"] = True, "ranked"
        out["chips"].append({"label": f"rank #{card.get('rank')}", "kind": "rank"})
        out["chips"].append({"label": str(card.get("tier") or "—"), "kind": "muted"})
        if card.get("cold_start"):
            out["chips"].append({"label": "cold-start", "kind": "warn"})
        out["evidence"] = [s for s in (str(card.get("signals", "")).split("; ")
                                       + str(card.get("reasons", "")).split("; ")) if s]
        out["watchouts"] = [s for s in str(card.get("watchouts", "")).split("; ") if s]
        metric("Followers", f"{int(card['followers']):,}" if _num(card.get("followers")) else "—")
        metric("Sales (30d)", f"${_num(card.get('total_gmv_30d')):,.0f}"
               if _num(card.get("total_gmv_30d")) is not None else "—")
        metric("Suggested product", card.get("suggested_product") or "—")
        metric("Niche", card.get("niche") or "—")

    # ── tier 2: in roster / creators, not ranked ─────────────────────────────────────────────
    elif ros or cre:
        out["found"], out["tier"] = True, "roster"
        out["chips"].append({"label": "in roster — not in ranked shortlist", "kind": "muted",
                             "hint": "metrics are real; the model hasn't scored them into current "
                                     "recommendations, so no rank or evidence trail yet."})
        status = str((ros or {}).get("sample_status") or "").strip()
        if status:
            out["chips"].append({"label": status, "kind": "muted"})
        gmv = _num((ros or {}).get("total_gmv_30d")) or 0.0
        dens = (intent_n / comment_n) if comment_n else 0.0
        tw = "STRONG" if gmv > 3000 else ("MODERATE" if gmv > 800 else "WEAK")
        out["outlook"] = {"tier": tw, "reason": f"${gmv:,.0f} 30-day sales · {dens:.0%} buy-intent in "
                                                 f"{comment_n} comments (playbook estimate, not a model score)"}
        metric("Followers", f"{int(cre['followers']):,}" if cre and _num(cre.get("followers")) else "—")
        metric("Sales (30d)", f"${gmv:,.0f}")
        metric("Tier", (ros or {}).get("tier") or "—")
        metric("Niche", (cre or {}).get("category") or "—")

    # ── tier 3: history-only / unknown ───────────────────────────────────────────────────────
    else:
        if shipped or len(orow):
            out["found"], out["tier"] = True, "history"
        else:
            out["note"] = ("brand-new creator, or the handle is spelled differently — no roster, sample, "
                           "or comment record for it.")
            return out

    # ── history rows appended to every found tier ────────────────────────────────────────────
    metric("Buy-intent comments", f"{intent_n} of {comment_n}" if comment_n else "no comments on record")
    if past_lift is not None:
        metric("Past sample result", f"{'+' if past_lift >= 0 else ''}${past_lift:,} incremental lift",
               hint="matched-control estimate from a prior sample")
    if shipped:
        metric("Content record", f"posted {posted} of {shipped} shipped samples")
    if recent:
        metric("Recent shipments", " · ".join(f"{r['date']} {r['status']}" for r in recent))
    return out
