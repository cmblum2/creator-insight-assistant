"""Per-campaign breakeven ROAS (synthetic twin). Reads the breakeven_roas column from the synthetic
campaigns table; a blank breakeven = a 'launch' campaign with no profitable ROAS (fix pricing, not
spend). Same shape as the production margin-based breakeven view."""
from functools import lru_cache

import pandas as pd

from app.config import CONTRACT

CHANNEL_BREAKEVEN = 1.86   # synthetic channel default


@lru_cache(maxsize=1)
def _camps():
    return pd.read_csv(CONTRACT["campaigns"])


def get_breakeven(campaign_id, campaign_name=""):
    df = _camps()
    row = df[df["campaign_id"].astype(str) == str(campaign_id)]
    if row.empty:
        return {"breakeven": CHANNEL_BREAKEVEN, "flag": None}
    be = row.iloc[0]["breakeven_roas"]
    if pd.isna(be) or str(be).strip() == "":
        return {"breakeven": None, "flag": "launch"}
    return {"breakeven": float(be), "flag": None}
