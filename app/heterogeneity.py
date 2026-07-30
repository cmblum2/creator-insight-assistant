"""CATE-lite (synthetic twin): which creator segments show the largest sampling treatment effect?
Subgroup mean of the refund-adjusted lift (did_lift_refadj) across audience-size / seller-size /
buy-intent tertiles, with bootstrap CIs. Insight only. Reads outcomes.csv + roster + insights."""
import json
from functools import lru_cache

import numpy as np
import pandas as pd

from app.config import CONTRACT

LABEL = "did_lift_refadj"


def _boot(x, n=2000, lo=5, hi=95):
    x = np.asarray(x, dtype=float)
    if len(x) < 3:
        return [None, None]
    rng = np.random.RandomState(11)
    m = [rng.choice(x, len(x), replace=True).mean() for _ in range(n)]
    return [round(float(np.percentile(m, lo))), round(float(np.percentile(m, hi)))]


@lru_cache(maxsize=1)
def _joined():
    om = pd.read_csv(CONTRACT["outcomes"])
    col = LABEL if LABEL in om.columns else "did_lift"
    om = om.dropna(subset=["creator_id", col])[["creator_id", col]].rename(columns={col: "lift"})
    ro = pd.read_csv(CONTRACT["roster"])[["creator_id", "total_gmv_30d"]].drop_duplicates("creator_id")
    ins = pd.read_csv(CONTRACT["creator_insights"]).drop_duplicates("creator_id").copy()
    ins["followers"] = ins["insight_json"].map(lambda j: json.loads(j).get("followerCount", 0))
    ins["intent"] = ins["insight_json"].map(
        lambda j: 1 if any("buy-intent" in s for s in json.loads(j).get("signals", [])) else 0)
    df = om.merge(ro, on="creator_id", how="left").merge(
        ins[["creator_id", "followers", "intent"]], on="creator_id", how="left")
    return df.fillna(0)


def _tertiles(df, feat, nice):
    s = df[feat]
    try:
        q = pd.qcut(s, 3, labels=["low", "mid", "high"], duplicates="drop")
        return [(f"{nice} {lab}", (q == lab).values) for lab in q.cat.categories]
    except (ValueError, TypeError):
        return [(f"{nice} =0", (s <= 0).values), (f"{nice} >0", (s > 0).values)]


@lru_cache(maxsize=1)
def heterogeneity():
    df = _joined()
    if df.empty:
        return {"note": "no outcomes"}
    overall = float(df["lift"].mean())
    segs, spreads = [], {}
    for feat, nice in [("followers", "audience size"), ("total_gmv_30d", "seller size"),
                       ("intent", "buy-intent")]:
        means = []
        for label, mask in _tertiles(df, feat, nice):
            sub = df[mask]
            if len(sub) < 8:
                continue
            m = float(sub["lift"].mean())
            means.append(m)
            segs.append({"dimension": nice, "segment": label, "n": int(len(sub)),
                         "mean_lift": round(m), "ci90": _boot(sub["lift"].values),
                         "vs_overall": round(m - overall)})
        if len(means) >= 2:
            spreads[nice] = round(max(means) - min(means))
    segs.sort(key=lambda s: -s["mean_lift"])
    top = max(spreads, key=spreads.get) if spreads else None
    return {"overall_mean_lift": round(overall), "n": int(len(df)), "segments": segs,
            "biggest_lever": ({"dimension": top, "high_minus_low_lift": spreads.get(top)} if top else None),
            "note": "subgroup CATE on synthetic sampling outcomes (bootstrap CIs); insight only, "
                    "not wired into ranking."}
