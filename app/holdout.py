"""Holdout — the controlled test, in two honest parts.

1. quasi_experiment(): runnable now on labeled history. Among sampled creators, compare realized
   incremental PROFIT for those the engine ranks in its top tier (would-pick = treatment) vs its
   bottom tier (status-quo = control). Observational (selection caveat), but it exercises the real
   readout (Welch test + CI) and gives a first $ estimate of the ranking's value.
2. forward ledger: assigns eligible creators to a randomized arm and persists it, so future cycles
   accumulate a true RCT. Deterministic + idempotent (md5 parity). Running it is what upgrades
   "strong causal correlation" to "proven incremental value".

Synthetic data; same math and framing as the production engine.
"""
import hashlib
import os

import pandas as pd

from app.config import CONTRACT, NET_MARGIN, SAMPLE_COST

LEDGER = "data/holdout_ledger.csv"


def _labeled_profit():
    om = pd.read_csv(CONTRACT["outcomes"]).dropna(subset=["rank_position"])
    col = "did_lift_refadj" if "did_lift_refadj" in om.columns else "did_lift"
    om["profit"] = NET_MARGIN * om[col].astype(float) - SAMPLE_COST
    return om.sort_values("rank_position")


def quasi_experiment():
    j = _labeled_profit()
    if len(j) < 20:
        return {"note": "not enough labeled samples"}
    from app.experiment import holdout_lift
    tert = len(j) // 3
    res = holdout_lift(j.head(tert)["profit"].tolist(), j.tail(tert)["profit"].tolist())
    res["design"] = ("retrospective natural experiment — engine top-tier vs bottom-tier rank among "
                     "sampled creators; observational (selection caveat), not randomized")
    return res


def _arm(cid):
    return "treatment" if int(hashlib.md5(str(cid).encode()).hexdigest(), 16) % 2 == 0 else "control"


def init_forward_ledger(top_n=120):
    """Assign eligible (not-seeded, not-control) creators to randomized arms and persist. Idempotent."""
    from app.recommend import _insights
    from app.enrich import enrich
    existing = {}
    if os.path.exists(LEDGER):
        existing = {r["creator_id"]: r["arm"] for _, r in pd.read_csv(LEDGER).iterrows()}
    rows, seen = [], set()
    for _, row in _insights().iterrows():
        cid = str(row["creator_id"])
        if cid in seen:
            continue
        seen.add(cid)
        if cid in existing:
            rows.append({"creator_id": cid, "arm": existing[cid], "rank": row["rank_position"]})
            continue
        e = enrich(cid)
        if e.get("seeded") or e.get("is_control"):
            continue
        rows.append({"creator_id": cid, "arm": _arm(cid), "rank": row["rank_position"]})
        if len(rows) >= top_n:
            break
    df = pd.DataFrame(rows)
    df.to_csv(LEDGER, index=False)
    return {"total": len(df), "treatment": int((df["arm"] == "treatment").sum()),
            "control": int((df["arm"] == "control").sum())}


def report():
    out = {"quasi_experiment": quasi_experiment()}
    if os.path.exists(LEDGER):
        led = pd.read_csv(LEDGER)
        out["forward_holdout_status"] = (f"ledger initialized: {len(led)} creators "
                                         f"({int((led['arm']=='treatment').sum())} treatment / "
                                         f"{int((led['arm']=='control').sum())} control) — accumulating outcomes")
    else:
        out["forward_holdout_status"] = "forward ledger not yet initialized"
    try:
        from app.economics import unit_economics
        from app.experiment import required_n_per_arm_proportion
        p0 = unit_economics().get("pct_roi_positive", 0.30)
        out["power_note"] = (f"~{required_n_per_arm_proportion(p0, min(p0 + 0.10, 0.99)):,}/arm to detect a "
                             f"{p0:.0%}->{p0+0.10:.0%} hit-rate lift (proportion test)")
    except Exception:
        pass
    return out
