"""Portfolio budget allocator — paid GMV-Max vs organic sampling, by marginal incremental profit.
Synthetic twin: reads campaigns.csv (paid) + outcomes.csv (sampling curve). Greedy: each dollar goes
where its expected incremental profit is highest, stopping when no lever has a profitable next dollar.
"""
from app.tenant import shop_cache

import pandas as pd

from app.breakeven import get_breakeven
from app.config import CONTRACT, NET_MARGIN, SAMPLE_COST
from app.decide import campaign_verdict

SATURATION = 0.7        # marginal ROAS as a fraction of current avg (flagged; no spend-response curve)
PAID_HEADROOM = 1.0
RANK_BUCKETS = [(1, 25), (26, 75), (76, 200), (201, 500), (501, 100000)]


@shop_cache
def _sampling_curve():
    om = pd.read_csv(CONTRACT["outcomes"])
    col = "did_lift_refadj" if "did_lift_refadj" in om.columns else "did_lift"
    om = om.dropna(subset=["rank_position", col])
    curve = []
    for lo, hi in RANK_BUCKETS:
        b = om[(om["rank_position"] >= lo) & (om["rank_position"] <= hi)]
        if len(b) < 3:
            continue
        exp = NET_MARGIN * float(b[col].mean()) - SAMPLE_COST
        curve.append({"rank_lo": lo, "rank_hi": min(hi, lo + 24) if hi > 9999 else hi,
                      "capacity": (hi - lo + 1) if hi < 9999 else 300,
                      "mean_lift": round(float(b[col].mean())), "profit_per_sample": round(exp, 2),
                      "n_obs": int(len(b))})
    return curve


def _campaigns():
    df = pd.read_csv(CONTRACT["campaigns"])
    out = []
    for r in df.itertuples():
        be = get_breakeven(str(r.campaign_id))
        v, _ = campaign_verdict(float(r.roas), float(r.target_roas), be["breakeven"], be["flag"],
                                str(r.status))
        out.append({"campaign": str(r.campaign_name), "verdict": v, "roas": float(r.roas),
                    "breakeven": be["breakeven"], "spend_30d": float(r.spend_30d)})
    return out


def allocate(budget, horizon_days=30):
    budget = float(budget)
    paid = []
    for c in _campaigns():
        be = c["breakeven"]
        if c["verdict"] not in ("SCALE", "TUNE") or not be or be <= 0:
            continue
        ret = (1.0 / be) * (c["roas"] * SATURATION) - 1.0
        if ret <= 0:
            continue
        paid.append({"campaign": c["campaign"], "verdict": c["verdict"], "roas": round(c["roas"], 2),
                     "return_per_dollar": round(ret, 3), "headroom": round(c["spend_30d"] * PAID_HEADROOM, 2)})
    paid.sort(key=lambda x: -x["return_per_dollar"])
    curve = [b for b in _sampling_curve() if b["profit_per_sample"] > 0]
    remaining = budget
    palloc = {p["campaign"]: {"$": 0.0, "return_per_dollar": p["return_per_dollar"], "verdict": p["verdict"]}
              for p in paid}
    n_samples, sample_profit, tiers, pi, ci, paid_profit = 0, 0.0, [], 0, 0, 0.0
    while remaining > 0:
        pr = paid[pi]["return_per_dollar"] if pi < len(paid) else -1
        sr = (curve[ci]["profit_per_sample"] / SAMPLE_COST) if ci < len(curve) else -1
        if pr <= 0 and sr <= 0:
            break
        if pr >= sr:
            take = min(paid[pi]["headroom"], remaining)
            palloc[paid[pi]["campaign"]]["$"] += round(take, 2)
            paid_profit += take * pr
            remaining -= take
            pi += 1
        else:
            t = curve[ci]
            k = min(t["capacity"], int(remaining // SAMPLE_COST))
            if k <= 0:
                break
            n_samples += k
            sample_profit += k * t["profit_per_sample"]
            remaining -= k * SAMPLE_COST
            tiers.append({"ranks": f"{t['rank_lo']}-{t['rank_hi']}", "n": k,
                          "profit_per_sample": t["profit_per_sample"], "based_on_n_obs": t["n_obs"]})
            ci += 1
    pout = sorted([{"campaign": k, **v} for k, v in palloc.items() if v["$"] > 0], key=lambda x: -x["$"])
    spent = budget - remaining
    return {
        "budget": round(budget, 2), "allocated": round(spent, 2), "unspent": round(remaining, 2),
        "paid_gmv_max": {"total": round(sum(p["$"] for p in pout), 2), "campaigns": pout},
        "sampling": {"total": round(n_samples * SAMPLE_COST, 2), "n_samples": n_samples,
                     "sample_cost": SAMPLE_COST, "tiers": tiers},
        "expected_incremental_profit": round(paid_profit + sample_profit),
        "split": {"paid_pct": round(sum(p["$"] for p in pout) / spent, 3) if spent else 0,
                  "sampling_pct": round(n_samples * SAMPLE_COST / spent, 3) if spent else 0},
        "assumptions": {"net_margin": NET_MARGIN, "sample_cost": SAMPLE_COST, "saturation": SATURATION,
                        "caveat": "synthetic; paid marginal = current ROAS x saturation (no spend-response "
                                  "curve); unspent = no lever had a profitable next dollar."},
    }
