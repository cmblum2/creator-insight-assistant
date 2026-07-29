"""Creator LTV + retention cohorts from the (synthetic) order timeline — is a sampled creator a
recurring revenue stream or one-and-done?

Reads data/orders.csv (creator_id, month_idx relative to first order, net_gmv). Answers the commercial
question a conversion-rate can't: repeat rate, one-and-done rate, a retention curve, and net-
contribution LTV. Same framing as the production engine; synthetic numbers here.
"""
from functools import lru_cache

import numpy as np
import pandas as pd

from app.config import CONTRACT, NET_MARGIN


@lru_cache(maxsize=1)
def _by_creator():
    df = pd.read_csv(CONTRACT["orders"])
    if df.empty:
        return None
    per = {}
    for cid, grp in df.groupby("creator_id"):
        months = set(int(m) for m in grp["month_idx"])
        per[cid] = {"months": months, "net_total": float(grp["net_gmv"].sum()), "first_idx": min(months)}
    return per


def retention_curve(horizon=5):
    """Share of creators still generating net sales k months after their first order (k=0..horizon).
    Right-censoring aware: denominator at k = creators observable that far."""
    per = _by_creator()
    if not per:
        return {"note": "no order data"}
    max_idx = max(mx for d in per.values() for mx in d["months"])
    curve = []
    for k in range(horizon + 1):
        obs = [d for d in per.values() if d["first_idx"] + k <= max_idx]
        if not obs:
            break
        active = sum(1 for d in obs if (d["first_idx"] + k) in d["months"])
        curve.append({"month": k, "retained": round(active / len(obs), 3), "observable_creators": len(obs)})
    return {"curve": curve, "note": "month 0 = first-order month; right-censoring aware."}


def ltv(net_margin=NET_MARGIN):
    """Net-contribution LTV per creator + repeat / one-and-done rates."""
    per = _by_creator()
    if not per:
        return {"note": "no order data"}
    ltvs = np.array([net_margin * d["net_total"] for d in per.values() if d["net_total"] > 0])
    n_months = np.array([len(d["months"]) for d in per.values()])
    n = len(per)
    return {
        "n_selling_creators": n,
        "median_ltv_net_contribution": round(float(np.median(ltvs)), 2) if len(ltvs) else 0.0,
        "mean_ltv_net_contribution": round(float(ltvs.mean()), 2) if len(ltvs) else 0.0,
        "repeat_rate": round(float((n_months >= 2).mean()), 3),
        "one_and_done_rate": round(float((n_months == 1).mean()), 3),
        "net_margin_used": net_margin,
        "note": "LTV = net contribution over the order window; a right-censored lower bound.",
    }
