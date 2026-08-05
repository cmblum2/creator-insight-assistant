"""Unit economics of a sample: does it make MONEY, and how fast does it pay back.

The sampling engine measures incremental refund-adjusted GMV per sample (the causal label). This layer
turns revenue into PROFIT and ROI — the number a commercial reviewer actually asks for:

    net incremental contribution = net_margin * incremental_refadj_GMV
    incremental profit           = net incremental contribution - sample_cost   (COGS + shipping)
    ROI                          = incremental profit / sample_cost

Drivers are named + defensible: net_margin = product contribution (40.5%) - affiliate commission
(10.5%) = 30%; sample_cost = $14 (COGS + ship), the one estimate, stress-tested in sensitivity().
Synthetic data here, but the same math and framing as the production engine.
"""
from app.tenant import shop_cache

import pandas as pd

from app.config import CONTRACT, NET_MARGIN, SAMPLE_COST, PRODUCT_CONTRIB, COMMISSION_RATE


@shop_cache
def _labeled_gmv():
    """Per sampled creator: refund-adjusted incremental GMV (did_lift_refadj) — the revenue the profit
    math is built on."""
    om = pd.read_csv(CONTRACT["outcomes"])
    col = "did_lift_refadj" if "did_lift_refadj" in om.columns else "did_lift"
    om = om.dropna(subset=["creator_id"])
    return om[["creator_id", "handle", col]].rename(columns={col: "inc_gmv"})


def unit_economics(net_margin=NET_MARGIN, sample_cost=SAMPLE_COST):
    """Per-creator profit & ROI over the labeled sample set, plus portfolio roll-up."""
    om = _labeled_gmv()
    if om.empty:
        return {"note": "no outcomes"}
    g = om["inc_gmv"].astype(float)
    net_contrib = net_margin * g
    profit = net_contrib - sample_cost
    roi = profit / sample_cost
    n = len(om)
    total_net = float(net_contrib.sum())
    total_cost = n * sample_cost
    return {
        "drivers": {"net_margin": net_margin, "sample_cost": sample_cost,
                    "product_contrib": PRODUCT_CONTRIB, "commission_rate": COMMISSION_RATE},
        "n_samples": n,
        "median_incremental_gmv": round(float(g.median()), 2),
        "median_incremental_profit": round(float(profit.median()), 2),
        "median_roi": round(float(roi.median()), 3),
        "pct_roi_positive": round(float((profit > 0).mean()), 3),
        "portfolio": {
            "incremental_gmv": round(float(g.sum())),
            "net_contribution": round(total_net),
            "sample_cost_total": round(total_cost),
            "incremental_profit": round(total_net - total_cost),
            "blended_roi": round((total_net - total_cost) / total_cost, 3) if total_cost else None,
            "margin_per_dollar_spent": round(total_net / total_cost, 2) if total_cost else None,
        },
    }


def size_the_prize(samples_per_month=500, net_margin=NET_MARGIN, sample_cost=SAMPLE_COST):
    """Forward opportunity: expected incremental profit per sample x a target monthly volume."""
    om = _labeled_gmv()
    if om.empty:
        return {"note": "no outcomes"}
    profit = net_margin * om["inc_gmv"].astype(float) - sample_cost
    ev = float(profit.mean())
    return {
        "expected_profit_per_sample": round(ev, 2),
        "samples_per_month": samples_per_month,
        "annual_incremental_profit": round(ev * samples_per_month * 12),
        "annual_sample_spend": round(sample_cost * samples_per_month * 12),
        "caveat": "expected value from n=%d labeled samples; a randomized holdout would de-bias it." % len(om),
    }


def sensitivity(margins=(0.20, 0.25, 0.30, 0.35, 0.40),
                sample_costs=(10.0, 14.0, 18.0, 22.0)):
    """Portfolio blended ROI across the margin x sample-cost grid — a defensible band, not a point."""
    om = _labeled_gmv()
    if om.empty:
        return {"note": "no outcomes"}
    g = om["inc_gmv"].astype(float)
    n = len(om)
    rows = []
    for m in margins:
        row = {"net_margin": m}
        for c in sample_costs:
            row[f"cost_{int(c)}"] = round((float((m * g).sum()) - n * c) / (n * c), 2)
        rows.append(row)
    return {"metric": "portfolio blended ROI (incremental profit / sample spend)", "rows": rows,
            "note": "each cell = ROI at (net_margin, sample_cost). Base case net_margin=0.30, cost=$14."}
