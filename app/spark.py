"""Spark timing (synthetic twin): ROAS by video age at first spark + organic winners to gate. The
money finding — sparking in the 8-14 day window beats sparking at launch — shows on synthetic data.
Reads videos.csv."""
from functools import lru_cache

import pandas as pd

from app.config import CONTRACT


@lru_cache(maxsize=1)
def spark_report():
    df = pd.read_csv(CONTRACT["videos"])
    sparked = df[df["ad_spend"].fillna(0) > 0].copy()
    sparked["roas"] = sparked["ad_gross_revenue"] / sparked["ad_spend"].clip(lower=1)

    def band(a):
        return "8-14d (sweet spot)" if 8 <= a <= 14 else ("<8d (early)" if a < 8 else "15+d (late)")

    sparked["band"] = sparked["age_days"].map(band)
    timing = []
    for b in ["<8d (early)", "8-14d (sweet spot)", "15+d (late)"]:
        seg = sparked[sparked["band"] == b]
        if len(seg):
            timing.append({"age_band": b, "avg_roas": round(float(seg["roas"].mean()), 2), "n": int(len(seg))})

    organic = df[(df["ad_spend"].fillna(0) == 0) & (df["gmv14"] > 300)].copy()
    cands = organic.sort_values("gmv14", ascending=False).head(10)
    return {
        "timing": timing,
        "candidates": [{"handle": r.username, "gmv14": round(float(r.gmv14)), "views14": int(r.views14),
                        "age_days": int(r.age_days)} for r in cands.itertuples()],
        "note": "synthetic; ROAS by age at spark + organic winners that need an ad boost.",
    }
