"""Recommender scorecard — does the ranking actually pick winners, and is it calibrated?

Runs on the synthetic outcomes (scripts/gen_data.py): each creator has a rank_position and a realized
refund-adjusted lift (did_lift_refadj). Three read-outs:
  * rank-IC: Spearman rank correlation between the engine's ranking and realized lift.
  * precision@K: of the top-K ranked creators, what share actually won (lift > 0), vs the base rate.
  * calibration: creators binned by rank; mean realized lift should rise as rank improves (monotonic).

Synthetic data only — no real creators, handles, or warehouse. This is the evaluation-discipline piece
the project exists to demonstrate.
"""
from functools import lru_cache

import pandas as pd

from app.config import CONTRACT


@lru_cache(maxsize=1)
def _labels():
    from pathlib import Path
    f = Path(CONTRACT["outcomes"])
    if not f.exists():
        return None
    df = pd.read_csv(f)
    col = "did_lift_refadj" if "did_lift_refadj" in df.columns else "did_lift"
    df = df.dropna(subset=["rank_position", col]).rename(columns={col: "lift"})
    df["rank_position"] = pd.to_numeric(df["rank_position"], errors="coerce")
    return df.dropna(subset=["rank_position"])


def _spearman(a, b):
    ra, rb = pd.Series(a).rank(), pd.Series(b).rank()
    if ra.std() == 0 or rb.std() == 0:
        return None
    return round(float(ra.corr(rb)), 3)


def recommender_scorecard():
    df = _labels()
    if df is None or df.empty:
        return {"note": "no synthetic outcomes — run scripts/gen_data.py"}
    df = df.sort_values("rank_position")
    n = len(df)
    base = float((df["lift"] > 0).mean())

    # rank-IC: better rank (lower number) should track higher lift -> use -rank so positive = good
    ic = _spearman(-df["rank_position"], df["lift"])

    pk = []
    for k in (10, 25, 50, 100):
        top = df.head(k)
        if len(top) < 3:
            continue
        pk.append({"k": k, "n": int(len(top)),
                   "precision": round(float((top["lift"] > 0).mean()), 3),
                   "median_lift": round(float(top["lift"].median()))})

    n_bins = 5 if n >= 40 else 3
    bins = []
    for i in range(n_bins):
        lo = i * n // n_bins
        hi = (i + 1) * n // n_bins
        seg = df.iloc[lo:hi]
        if len(seg) < 2:
            continue
        bins.append({"bin": i + 1, "n": int(len(seg)),
                     "rank_range": f"{int(seg['rank_position'].min())}-{int(seg['rank_position'].max())}",
                     "mean_lift": round(float(seg["lift"].mean()))})
    means = [b["mean_lift"] for b in bins]
    monotonic = all(means[i] >= means[i + 1] for i in range(len(means) - 1))  # best rank first -> decreasing

    return {
        "n": n,
        "rank_ic": ic,
        "base_win_rate": round(base, 3),
        "precision_at_k": pk,
        "calibration": {"bins": bins, "monotonic": bool(monotonic),
                        "top_minus_bottom_lift": round(means[0] - means[-1]) if len(means) >= 2 else None,
                        "note": "creators binned by rank (best first); mean realized lift should fall "
                                "as rank worsens."},
        "note": "synthetic data (scripts/gen_data.py); rank-IC = Spearman(rank, realized lift).",
    }
