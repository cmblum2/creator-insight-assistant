"""Retrospective scorecard (synthetic twin): the sample -> sold funnel, the power-law that separates
winners, and the mid-funnel diagnosis. Reads outcomes.csv + the post-funnel."""
from app.tenant import shop_cache

import pandas as pd

from app.config import CONTRACT


@shop_cache
def scorecard():
    om = pd.read_csv(CONTRACT["outcomes"])
    col = "did_lift_refadj" if "did_lift_refadj" in om.columns else "did_lift"
    n = len(om)
    winners = om[om[col] > 0]
    won = int(len(winners))
    from app.post_rate import funnel as pf
    f = pf()
    return {
        "n_samples": n, "winners": won, "win_rate": round(won / n, 3) if n else 0,
        "total_incremental_gmv": round(float(winners[col].sum())),
        "median_winner_lift": round(float(winners[col].median())) if won else 0,
        "median_sample_lift": round(float(om[col].median()), 1),
        "funnel": {"shipped": f["shipped"], "posted": f["posted_content"], "post_rate": f["post_rate"],
                   "post_to_sale_rate": f["post_to_sale_rate"]},
        "note": "synthetic retrospective — a power law: the median sample barely moves, a few big "
                "winners carry the portfolio (which is exactly why the ranking matters).",
    }


def sampling_trends():
    return {"note": "monthly sample-cohort trend omitted at this synthetic scale"}


def funnel_diagnosis():
    from app.post_rate import funnel
    f = funnel()
    return {"wasted_spend_rate": f["wasted_spend_rate"],
            "diagnosis": f"{f['shipped_no_content']} of {f['shipped']} samples shipped but never became "
                         f"content ({f['wasted_spend_rate']:.0%}) — the mid-funnel leak to watch."}
