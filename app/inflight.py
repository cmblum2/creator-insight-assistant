"""Samples in flight (synthetic twin): the 'shepherding' view between 'who to sample' and the
weeks-later retrospective. Classifies each recently-shipped sample by state (sold/posted/cold/waiting)
from fulfillment status (sample_requests.csv) + attributed lift (outcomes.csv), then rolls up per
ship-week and surfaces a nudge list of samples that have gone quiet.

State per shipped sample, evaluated in order (first match wins):
  sold    -> Completed AND creator has attributed revenue (did_lift_refadj>0)
  posted  -> Completed AND no revenue yet
  cold    -> platform says no content, OR 21+ days quiet and not sold
  waiting -> recent Shipped / Ready to Ship
"""
from datetime import date

import pandas as pd

from app.config import CONTRACT

AS_OF = date(2026, 7, 30)
WINDOW_DAYS = 60
COLD_AGE_DAYS = 21
NUDGE_CAP = 24
JUST_SOLD_CAP = 12

NO_CONTENT = ("Content Unfulfilled", "Content Pending")

NOTE = ("synthetic; state from fulfillment status + attributed lift. "
        "'cold' = platform says no content, or 21+ days quiet.")


def _at(h):
    """Display a handle as '@name' regardless of stored form."""
    return "@" + str(h).lstrip("@")


def _empty():
    return {
        "n": 0,
        "summary": {"sold": 0, "posted": 0, "cold": 0, "waiting": 0},
        "weeks": [],
        "nudge": [],
        "nudge_overflow": 0,
        "just_sold": [],
        "note": NOTE,
    }


def _revenue_by_handle():
    """Map creator_handle (stripped of '@') -> attributed lift, using did_lift_refadj with a
    did_lift fallback. Only handles with lift > 0 count as 'has revenue'."""
    o = pd.read_csv(CONTRACT["outcomes"])
    if o.empty or "handle" not in o.columns:
        return {}
    lift = o.get("did_lift_refadj")
    if lift is None:
        lift = o.get("did_lift")
    o = o.assign(jlift=pd.to_numeric(lift, errors="coerce").fillna(
        pd.to_numeric(o.get("did_lift"), errors="coerce")).fillna(0.0))
    o["jkey"] = o["handle"].astype(str).str.lstrip("@")
    # if a handle appears more than once, keep its strongest lift
    return o.groupby("jkey")["jlift"].max().to_dict()


def samples_in_flight():
    """Return in-flight sample states, weekly rollups, and a nudge list (see module docstring)."""
    try:
        s = pd.read_csv(CONTRACT["sample_requests"])
    except Exception as e:  # missing/unreadable file
        return {"note": f"unavailable: {str(e)[:180]}"}
    try:
        rev = _revenue_by_handle()
    except Exception:
        rev = {}

    if s.empty or "shipped_time" not in s.columns:
        return _empty()

    s = s.copy()
    s["shipped_dt"] = pd.to_datetime(s["shipped_time"], errors="coerce")
    s = s[s["shipped_dt"].notna()]
    as_of_ts = pd.Timestamp(AS_OF)
    s["age_days"] = (as_of_ts - s["shipped_dt"]).dt.days
    # in-flight = shipped within the last 60 days (and not in the future)
    s = s[(s["age_days"] >= 0) & (s["age_days"] <= WINDOW_DAYS)]
    if s.empty:
        return _empty()

    s["jkey"] = s["creator_handle"].astype(str).str.lstrip("@")
    s["jlift"] = s["jkey"].map(rev).fillna(0.0)

    def classify(row):
        status = row["status"]
        completed = status == "Completed"
        has_rev = row["jlift"] > 0
        if completed and has_rev:
            return "sold"
        if completed and not has_rev:
            # a Completed-no-revenue sample gone quiet too long slips to 'cold'
            if row["age_days"] >= COLD_AGE_DAYS:
                return "cold"
            return "posted"
        if status in NO_CONTENT or (row["age_days"] >= COLD_AGE_DAYS):
            return "cold"
        return "waiting"

    s["state"] = s.apply(classify, axis=1)

    summary = {st: int((s["state"] == st).sum()) for st in ("sold", "posted", "cold", "waiting")}
    n = int(len(s))

    # per ship-week rollup, keyed by the Monday of that week
    s["week_start"] = s["shipped_dt"].dt.to_period("W-SUN").dt.start_time
    weeks = []
    for wk, grp in s.groupby("week_start"):
        row = {st: int((grp["state"] == st).sum()) for st in ("waiting", "posted", "sold", "cold")}
        label = f"{wk.strftime('%b')} {wk.day}"  # e.g. "Jul 21"; %-d is not portable to Windows
        row = {"label": label, **row, "total": int(len(grp))}
        weeks.append((wk, row))
    weeks.sort(key=lambda x: x[0], reverse=True)  # newest first
    weeks = [w for _, w in weeks]

    # nudge: cold samples, oldest first, one per creator, capped
    cold = s[s["state"] == "cold"].sort_values("age_days", ascending=False)
    seen = set()
    nudge_all = []
    for r in cold.itertuples():
        if r.jkey in seen:
            continue
        seen.add(r.jkey)
        nudge_all.append({"handle": _at(r.creator_handle), "days": int(r.age_days)})
    nudge = nudge_all[:NUDGE_CAP]
    nudge_overflow = max(len(nudge_all) - NUDGE_CAP, 0)

    # just_sold: highest attributed lift first, capped
    sold = s[s["state"] == "sold"].sort_values("jlift", ascending=False)
    seen_s = set()
    just_sold = []
    for r in sold.itertuples():
        if r.jkey in seen_s:
            continue
        seen_s.add(r.jkey)
        just_sold.append({"handle": _at(r.creator_handle), "lift": int(round(r.jlift))})
        if len(just_sold) >= JUST_SOLD_CAP:
            break

    return {
        "n": n,
        "summary": summary,
        "weeks": weeks,
        "nudge": nudge,
        "nudge_overflow": nudge_overflow,
        "just_sold": just_sold,
        "note": NOTE,
    }
