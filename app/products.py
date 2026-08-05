"""Product dropdown + leaf-level product-fit (synthetic twin). Dropdown from the insights'
suggested_product; leaf product-type audience via creator_videos x product_categories."""
from app.tenant import shop_cache

import pandas as pd

from app.config import CONTRACT


@shop_cache
def products():
    s = pd.read_csv(CONTRACT["creator_insights"])["suggested_product"].dropna().astype(str)
    vc = s[s.str.strip() != ""].value_counts()
    return {"products": [{"name": p, "n": int(n)} for p, n in vc.items()][:40]}


@shop_cache
def _cats():
    df = pd.read_csv(CONTRACT["product_categories"])
    df["product_id"] = df["product_id"].astype(str)
    return df


@shop_cache
def product_leaf(search):
    s = (search or "").strip().lower()
    if not s:
        return []
    cats = _cats()
    m = cats[cats["product_name"].str.lower().str.contains(s, na=False, regex=False)]
    return sorted(m["leaf_category"].dropna().unique().tolist())


@shop_cache
def leaf_creators(search):
    leaves = product_leaf(search)
    if not leaves:
        return frozenset()
    cats = _cats()
    cv = pd.read_csv(CONTRACT["creator_videos"])
    cv["product_id"] = cv["product_id"].astype(str)
    pids = set(cats[cats["leaf_category"].isin(leaves)]["product_id"])
    return frozenset(cv[cv["product_id"].isin(pids)]["creator_handle"].dropna().unique())
