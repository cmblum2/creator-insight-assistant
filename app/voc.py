"""Voice of Customer (synthetic twin) — themes across the comment corpus: category mix, competitor
board (with the positioning wedge), price/praise samples, and a VALIDATED action (comparison-shopping
audiences convert worse). Reads comments.csv (category + text). Competitor names are 100% fake."""
import os
from collections import Counter
from functools import lru_cache

import pandas as pd

from app.config import CONTRACT

COMPETITORS = ["WaveLux", "SleekPro", "CurlCraft"]


@lru_cache(maxsize=1)
def _comments():
    return pd.read_csv(CONTRACT["comments"])


@lru_cache(maxsize=1)
def voc():
    df = _comments()
    n = len(df)
    mix = {k: round(v / n, 3) for k, v in Counter(df["category"]).most_common()}
    board = []
    for comp in COMPETITORS:
        cnt = int(df["comment_text"].str.contains(comp, case=False, na=False).sum())
        if cnt:
            board.append({"competitor": comp, "mentions": cnt})
    board.sort(key=lambda x: -x["mentions"])
    price = df[df["category"] == "price"]
    praise = df[df["category"] == "praise"]
    return {
        "total": n, "category_mix": mix, "competitor_board": board,
        "price": {"n": int(len(price)), "samples": price["comment_text"].drop_duplicates().head(3).tolist()},
        "praise": {"n": int(len(praise)), "samples": praise["comment_text"].drop_duplicates().head(3).tolist()},
        "note": "themes over the synthetic comment corpus; competitor names are fake.",
    }


def action_list():
    from app.theme_lift import video_associations
    v = voc()
    board = v["competitor_board"]
    actions = []
    if board:
        top = board[0]
        actions.append({"action": f"Position against {top['competitor']} — the competitor most named in your "
                                  f"audience's comments ({top['mentions']} mentions). Preempt it in briefs.",
                        "tag": "qualitative"})
    comp = next((a for a in video_associations().get("associations", []) if a["theme"] == "comparison"), None)
    if comp and comp.get("significant"):
        actions.append({"action": f"De-prioritize creators whose audience comparison-shops — comparison "
                                  f"share is negatively associated with conversion (Spearman {comp['r']}, "
                                  f"a validated warning sign, not a buy signal).", "tag": "validated"})
    if v["category_mix"].get("price", 0) > 0:
        actions.append({"action": "Price shows up as value-positioning, not sticker shock — lead with "
                                  "'does the same for less' framing.", "tag": "qualitative"})
    return {"actions": actions, "note": "validated actions change ranking; qualitative ones brief humans."}


def narrate():
    """LLM positioning read over the VoC boards (needs ANTHROPIC_API_KEY)."""
    if not os.getenv("ANTHROPIC_API_KEY"):
        return {"note": "ANTHROPIC_API_KEY not set — narrate unavailable (the boards above are deterministic)"}
    import anthropic
    v = voc()
    prompt = (f"You are a brand strategist. Here is synthetic Voice-of-Customer data: category mix "
              f"{v['category_mix']}, competitor board {v['competitor_board']}, price samples "
              f"{v['price']['samples']}. In 3 sentences, give the positioning 'so what' — the wedge "
              f"against the top competitor and how to use price framing.")
    try:
        cl = anthropic.Anthropic()
        msg = cl.messages.create(model="claude-haiku-4-5-20251001", max_tokens=300,
                                 messages=[{"role": "user", "content": prompt}])
        return {"narrative": msg.content[0].text}
    except Exception as e:
        return {"note": f"narrate unavailable: {str(e)[:120]}"}
