"""Deterministic sampling recommendations — no LLM, instant, free.

Eligible = not already seeded, not a matched control. Sorted by ordinal rank (the only
sanctioned use of the scores). The LLM (/ask) is for follow-up questions, not the ranking.
"""
import json
from functools import lru_cache

import pandas as pd

from app.config import CONTRACT
from app.enrich import enrich


def _s(v):
    if v in (None, "", []):
        return ""
    if isinstance(v, list):
        return "; ".join(filter(None, (_s(x) for x in v)))
    if isinstance(v, dict):
        return ", ".join(f"{k}={_s(x)}" for k, x in v.items() if x not in (None, "", []))
    return str(v)


@lru_cache(maxsize=1)
def _insights():
    df = pd.read_csv(CONTRACT["creator_insights"]).fillna("")
    df["rank_position"] = pd.to_numeric(df["rank_position"], errors="coerce")
    return df.sort_values("rank_position")


def recommend(product: str = "", n: int = 10) -> dict:
    # multiple rows per creator (one per product line) — keep each creator once, best rank
    candidates, excluded, seen = [], {"seeded": 0, "control": 0}, set()
    for _, row in _insights().iterrows():
        if product and product.lower() not in str(row["suggested_product"]).lower():
            continue
        if row["creator_id"] in seen:
            continue
        seen.add(row["creator_id"])
        e = enrich(str(row["creator_id"]))
        if e["seeded"]:
            excluded["seeded"] += 1
            continue
        if e["is_control"]:
            excluded["control"] += 1
            continue
        try:
            j = json.loads(row["insight_json"])
        except (TypeError, ValueError):
            j = {}
        candidates.append({
            "handle": j.get("handle") or row["creator_id"],
            "creator_id": row["creator_id"],
            "rank": int(row["rank_position"]),
            "suggested_product": str(row["suggested_product"]),
            "niche": _s(j.get("niche")),
            "followers": j.get("followerCount"),
            "trust": j.get("trustAdjScore"),
            "cold_start": bool(j.get("coldStart")),
            "tier": e.get("tier", ""),
            "total_gmv_30d": e.get("total_gmv_30d", ""),
            "sample_status": e.get("sample_status", ""),
            "signals": _s(j.get("signals")),
            "reasons": _s(j.get("reasons")),
            "watchouts": _s(j.get("watchouts")),
        })
        if len(candidates) >= n:
            break
    return {"model": "deterministic-ordinal-v1", "product_filter": product,
            "candidates": candidates, "excluded": excluded}
