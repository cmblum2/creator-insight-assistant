"""Portfolio buy-intent summary (synthetic twin): purchase-category comments per creator + overall
density. Reads comments.csv (category)."""
from functools import lru_cache

import pandas as pd

from app.config import CONTRACT


@lru_cache(maxsize=1)
def intent_summary():
    df = pd.read_csv(CONTRACT["comments"])
    df["is_intent"] = df["category"].isin(["purchase", "confirmed_purchase"]).astype(int)
    g = df.groupby("handle").agg(comments=("category", "size"), intent=("is_intent", "sum"))
    g["density"] = (g["intent"] / g["comments"]).round(3)
    top = g[g["comments"] >= 10].sort_values("density", ascending=False).head(10)
    total, intent_total = len(df), int(df["is_intent"].sum())
    return {
        "total_comments": total, "intent_comments": intent_total,
        "overall_density": round(intent_total / total, 3) if total else 0,
        "top_creators": [{"handle": h, "comments": int(r.comments), "intent": int(r.intent),
                          "density": float(r.density)} for h, r in top.iterrows()],
        "note": "synthetic buy-intent = purchase + confirmed_purchase comment categories.",
    }
