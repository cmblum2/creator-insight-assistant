"""Decision queue — one ranked "Act today" list across GMV-Max campaigns, spark timing, and sampling.
Synthetic twin of the production engine: identical verdict logic + plain-English why-lines, reading the
synthetic campaigns / videos tables instead of the warehouse.
"""
from datetime import datetime, timezone
from app.tenant import shop_cache

import pandas as pd

from app.breakeven import get_breakeven
from app.config import CONTRACT

# velocity thresholds (synthetic)
VEL_VIEWS_STRONG, VEL_GMV_STRONG, VEL_CTR_STRONG = 8000, 200, 0.015
WINDOW_LO, WINDOW_HI = 8, 14


def campaign_verdict(roas, target, breakeven, flag, status):
    """The GMV-Max scale/cut decision tree (pure function — identical to production).
      GATE     negative pre-ad margin OR breakeven>8 (product-mix/pricing) — not a spend lever
      PAUSED   disabled — reference only
      RETARGET bid target set below breakeven — even hitting target loses money
      SCALE    hitting its bid target — raise budget
      TUNE     profitable (roas>=breakeven) but under target — target throttles spend
      CUT      below breakeven — losing money
    """
    if flag == "launch":
        return "GATE", 1.2
    if str(status).upper() == "DISABLE":
        return "PAUSED", 0.5
    if breakeven and breakeven > 8:      # a >8 breakeven is a product-mix/pricing problem, not retargetable
        return "GATE", 1.2
    if breakeven and target < breakeven:
        return "RETARGET", 2.6
    if roas >= target:
        return "SCALE", 3.0
    if breakeven and roas >= breakeven:
        return "TUNE", 1.8
    return "CUT", 2.8


def _campaign_actions():
    df = pd.read_csv(CONTRACT["campaigns"])
    out = []
    for r in df.itertuples():
        roas = float(r.roas)
        spend = float(r.spend_30d)
        target = float(r.target_roas)
        name = str(r.campaign_name)
        status = str(r.status).upper()
        budget = f"${float(r.budget_amount):,.0f}/day"
        be = get_breakeven(str(r.campaign_id), name)
        breakeven = be["breakeven"]
        why = [f"Spent ${spend:,.0f} so far, earning ${roas:.2f} back for every $1 spent (ROAS {roas:.2f}) "
               f"against a {target:.1f} goal. Running {budget} across {int(r.videos)} videos."]
        if breakeven:
            why.append(f"Break-even is ${breakeven:.2f} back per $1 (breakeven ROAS {breakeven:.2f}) — "
                       f"under that it loses money after all costs.")
        verdict, urgency = campaign_verdict(roas, target, breakeven, be["flag"], status)
        if verdict == "GATE":
            if breakeven and breakeven > 8:
                act = (f"→ Break-even needs ${breakeven:.0f} back per $1 — a product-mix / pricing "
                       f"problem, not something a bid target can fix. Don't raise the target.")
            else:
                act = ("→ The product sells for less than it costs to make — no ad result turns a profit. "
                       "Fix PRICING first, don't change spend.")
        elif verdict == "RETARGET":
            act = (f"→ The {target:.1f} goal is set below the ${breakeven:.2f} break-even, so even a "
                   f"'successful' campaign loses money. Raise the goal to at least {breakeven:.2f} "
                   f"(earning ${roas:.2f} back now, {budget}).")
        elif verdict == "SCALE":
            act = f"→ Winning — it's hitting the {target:.1f} goal. Give it more room: raise the daily budget above {budget}."
        elif verdict == "TUNE":
            act = (f"→ Profitable (earning ${roas:.2f} back, above the ${breakeven:.2f} break-even) but under "
                   f"its {target:.1f} goal — TikTok is holding spend back. Lower the goal to unlock it.")
        else:  # CUT
            act = (f"→ Losing money — earning ${roas:.2f} back but needs ${breakeven:.2f} to break even. "
                   f"Pause this campaign ({budget}).")
        why.append(act)
        out.append({"action": verdict, "type": "campaign", "target": name,
                    "campaign_id": str(r.campaign_id), "title": f"{int(r.videos)} videos · target {target:.1f}",
                    "why": why, "impact": round(spend * urgency)})
    return out


def _video_actions(limit=12):
    df = pd.read_csv(CONTRACT["videos"])
    df = df[df["ad_spend"].fillna(0) == 0]           # organic, un-sparked = spark candidates
    acts = []
    for r in df.itertuples():
        age = int(r.age_days)
        vpd, gpd, ctr = float(r.views_per_day), float(r.gmv_per_day), float(r.ctr)
        gmv14 = float(r.gmv14)
        views14 = int(r.views14)
        fresh = age <= 21
        hot = vpd >= VEL_VIEWS_STRONG or gpd >= VEL_GMV_STRONG or ctr >= VEL_CTR_STRONG
        why = [f"Earned ${gmv14:,.0f} in sales from {views14:,} views on its own — $0 spent on ads."]
        if fresh and hot and WINDOW_LO <= age <= WINDOW_HI:
            verdict, urgency = "SPARK NOW", 3.5
            why.append(f"→ It's {age} days old — right in the {WINDOW_LO}-{WINDOW_HI} day sweet spot where ad "
                       f"spend behind a proven organic video pays off best. Spark it now.")
        elif fresh and hot and age < WINDOW_LO:
            verdict, urgency = "WATCH", 2.5
            why.append(f"→ Taking off fast at {age} days old, but early — wait until day {WINDOW_LO} to spark it.")
        elif fresh and hot:
            verdict, urgency = "SPARK NOW", 2.8
            why.append(f"→ Strong momentum but already {age} days old, aging out of the window — spark it now.")
        elif fresh:
            verdict, urgency = "HOLD", 0.8
            why.append(f"→ Only {age} days old and not gaining enough speed yet — hold and watch.")
        elif gmv14 > 300:
            verdict, urgency = "REVIVE?", 1.5
            why.append(f"→ {age} days old but still selling on its own — a candidate to put ad spend behind.")
        else:
            continue
        score = (vpd + gpd * 20 + gmv14) * urgency
        acts.append({"action": verdict, "type": "spark", "target": f"{r.username}",
                     "video_id": str(r.video_id), "title": str(r.title)[:48], "why": why,
                     "impact": round(score)})
    acts.sort(key=lambda a: -a["impact"])
    return acts[:limit]


def _sample_actions(limit=8):
    from app.recommend import recommend
    out = []
    for c in recommend(n=limit).get("candidates", []):
        why = [f"Ranked #{c.get('rank')} out of the whole roster."]
        sig = c.get("signals") or c.get("reasons")
        if sig:
            why.append(sig if isinstance(sig, str) else "; ".join(sig))
        out.append({"action": "SAMPLE", "type": "sample", "target": c.get("handle"),
                    "why": why, "impact": round(max(0, 2000 - int(c.get("rank", 2000))))})
    return out


@shop_cache
def decision_queue():
    q = _video_actions() + _sample_actions() + _campaign_actions()
    q.sort(key=lambda a: -a["impact"])
    return {"generated": datetime.now(timezone.utc).isoformat()[:16], "queue": q,
            "note": "impact is an ordinal priority, not a dollar forecast (synthetic data)"}
