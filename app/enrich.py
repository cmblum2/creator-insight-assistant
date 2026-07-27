"""Structured joins from the sampling-engine tables — numbers joined at answer time, not embedded.

Guardrails: ordinal-only ranks (never spend-size), never recommend matched controls
(seeding a control contaminates lift measurement), flag already-seeded creators.
Tables are optional — missing/empty files degrade gracefully.
"""
from functools import lru_cache

import pandas as pd

from app.config import CONTRACT


def _read(name):
    try:
        return pd.read_csv(CONTRACT[name])
    except (FileNotFoundError, pd.errors.EmptyDataError):
        return pd.DataFrame()


@lru_cache(maxsize=1)
def _tables():
    roster = _read("roster").fillna("")
    if len(roster):
        roster = (roster.sort_values("as_of_date")
                  .groupby("creator_id", as_index=False).last().set_index("creator_id"))
    dec = _read("seeding_decisions")
    seeded = set(dec.query("seeded == True or seeded == 'True'")["creator_id"]) \
        if len(dec) else set()
    ctl = _read("seeding_controls")
    controls = set(ctl["control_creator_id"]) if len(ctl) else set()
    return roster, seeded, controls


def enrich(creator_id: str) -> dict:
    roster, seeded, controls = _tables()
    out = {"creator_id": creator_id,
           "seeded": creator_id in seeded,
           "is_control": creator_id in controls}
    if len(roster) and creator_id in roster.index:
        row = roster.loc[creator_id]
        out.update({"tier": str(row.get("tier", "")),
                    "total_gmv_30d": str(row.get("total_gmv_30d", "")),
                    "sample_status": str(row.get("sample_status", ""))})
    return out


def fact_line(e: dict) -> str:
    bits = []
    if e.get("tier"):
        bits.append(f"tier {e['tier']}")
    if e.get("total_gmv_30d"):
        bits.append(f"30d GMV ${e['total_gmv_30d']}")
    if e.get("sample_status"):
        bits.append(f"sample status: {e['sample_status']}")
    if e["seeded"]:
        bits.append("ALREADY SEEDED")
    if e["is_control"]:
        bits.append("MATCHED CONTROL - DO NOT RECOMMEND SAMPLING")
    return "quant facts: " + (", ".join(bits) if bits else "none on file")
