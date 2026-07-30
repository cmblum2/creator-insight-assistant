"""Sample -> post -> sale funnel (synthetic twin): does a shipped sample become content, and does it
sell? Reads sample_requests.csv (Euka's own fulfillment status: 'Completed' = content delivered,
'Content Unfulfilled'/'Pending' = the leak) + creator_videos.csv (revenue on the posted product)."""
from functools import lru_cache

import pandas as pd

from app.config import CONTRACT

FULFILLED = "Completed"
NO_CONTENT = ("Content Unfulfilled", "Content Pending")
GOT_PRODUCT = (FULFILLED, "Shipped", "Ready to Ship") + NO_CONTENT


@lru_cache(maxsize=1)
def _data():
    s = pd.read_csv(CONTRACT["sample_requests"])
    v = pd.read_csv(CONTRACT["creator_videos"])
    s["product_id"] = s["product_id"].astype(str)
    v["product_id"] = v["product_id"].astype(str)
    return s, v


@lru_cache(maxsize=1)
def funnel():
    s, v = _data()
    s = s[s["status"].isin(GOT_PRODUCT)]
    shipped = len(s)
    posted = int((s["status"] == FULFILLED).sum())
    no_content = int(s["status"].isin(NO_CONTENT).sum())
    vk = {k: float(val) for k, val in v.groupby(["creator_handle", "product_id"])["revenue"].sum().items()}
    comp = s[s["status"] == FULFILLED]
    sold = sum(1 for r in comp.itertuples() if vk.get((r.creator_handle, r.product_id), 0) > 0)
    return {
        "shipped": shipped, "posted_content": posted,
        "post_rate": round(posted / shipped, 3) if shipped else None,
        "shipped_no_content": no_content,
        "wasted_spend_rate": round(no_content / shipped, 3) if shipped else None,
        "posted_and_sold": sold,
        "post_to_sale_rate": round(sold / posted, 3) if posted else None,
        "note": "'post' = 'Completed' (content delivered); leak = 'Content Unfulfilled'/'Pending'. "
                "'sold' = the Completed sample's (creator, product) has a video with revenue (synthetic).",
    }


@lru_cache(maxsize=1)
def creator_post_rate(min_shipped=3):
    s, _ = _data()
    s = s[s["status"].isin(GOT_PRODUCT)].copy()
    s["posted"] = (s["status"] == FULFILLED).astype(int)
    g = s.groupby("creator_handle").agg(shipped=("status", "size"), posted=("posted", "sum"))
    g = g[g["shipped"] >= min_shipped]
    return {h: {"shipped": int(r.shipped), "posted": int(r.posted),
                "post_rate": round(float(r.posted) / float(r.shipped), 3)} for h, r in g.iterrows()}
