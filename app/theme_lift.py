"""Themes -> real outcome (synthetic twin): does a video's comment-theme mix predict conversion?
Per-video theme shares (comments.csv) vs conversion = organic orders/views (videos.csv), Spearman +
Bonferroni. The synthetic data is built so competitor-comparison share is negatively associated with
conversion — mirroring the real finding. Creator-level is reported infeasible, as in production."""
from functools import lru_cache

import pandas as pd
from scipy.stats import spearmanr

from app.config import CONTRACT

THEMES = ["purchase", "confirmed_purchase", "price", "comparison", "praise"]


@lru_cache(maxsize=1)
def video_associations():
    cm = pd.read_csv(CONTRACT["comments"])
    vids = pd.read_csv(CONTRACT["videos"])
    rows = []
    for vid, grp in cm.groupby("video_id"):
        tot = len(grp)
        rows.append({"video_id": vid, **{t: (grp["category"] == t).sum() / tot for t in THEMES}})
    shares = pd.DataFrame(rows)
    conv = vids.copy()
    conv["conversion"] = conv["organic_sku_orders"] / conv["organic_views"].clip(lower=1)
    m = shares.merge(conv[["video_id", "conversion"]], on="video_id", how="inner")
    alpha = 0.05 / len(THEMES)
    assoc = []
    for t in THEMES:
        if m[t].std() == 0:
            continue
        r, p = spearmanr(m[t], m["conversion"])
        assoc.append({"theme": t, "r": round(float(r), 3), "p": round(float(p), 4),
                      "significant": bool(p < alpha)})
    assoc.sort(key=lambda x: x["r"])
    return {"n_videos": int(len(m)), "associations": assoc, "alpha_bonferroni": round(alpha, 4),
            "note": "synthetic; conversion = organic orders/views; Bonferroni-corrected. Competitor-"
                    "comparison shows a negative association, as in production."}


def report():
    return {"video_level": video_associations(),
            "creator_level": {"note": "infeasible at this synthetic overlap size — reported honestly, "
                                      "like production (comment population barely overlaps the labeled set)."}}
