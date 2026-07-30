"""LLM-grounding features (synthetic twin): creator brief, verdict explain, and agentic hybrid query.
Each grounds a Claude call in the synthetic comments / videos / campaigns, and degrades gracefully to a
'no key' note (the grounding data is deterministic; the LLM adds the narrative). Live on Render where
ANTHROPIC_API_KEY is set."""
import os
from functools import lru_cache

import pandas as pd

from app.config import ANSWER_MODEL, CONTRACT


def _no_key():
    return {"note": "ANTHROPIC_API_KEY not set — this LLM feature needs a key (grounding data is "
                    "deterministic; set the key on Render to see the narrative)."}


def _claude(prompt, max_tokens=600):
    import anthropic
    cl = anthropic.Anthropic()
    msg = cl.messages.create(model=ANSWER_MODEL, max_tokens=max_tokens,
                             messages=[{"role": "user", "content": prompt}])
    # grab the first TEXT block (some models emit a thinking block before the text one)
    for block in msg.content:
        t = getattr(block, "text", None)
        if t:
            return t
    return ""


@lru_cache(maxsize=1)
def _comments():
    return pd.read_csv(CONTRACT["comments"])


def generate_brief(product, handle=None):
    """Creative brief (hook / proof / preempt / CTA) grounded in the product's top videos + audience comments."""
    if not os.getenv("ANTHROPIC_API_KEY"):
        return _no_key()
    vids = pd.read_csv(CONTRACT["videos"])
    cm = _comments()
    pv = vids[vids["canonical_name"].str.contains(product, case=False, na=False)] if product else vids
    top = pv.sort_values("gmv14", ascending=False).head(5)
    captions = top["title"].tolist()
    rel = cm[cm["video_id"].isin(set(top["video_id"]))]
    intent = rel[rel["category"].isin(["purchase", "confirmed_purchase"])]["comment_text"].drop_duplicates().head(5).tolist()
    objection = rel[rel["category"].isin(["price", "comparison"])]["comment_text"].drop_duplicates().head(5).tolist()
    praise = rel[rel["category"] == "praise"]["comment_text"].drop_duplicates().head(5).tolist()
    from app.voc import voc
    board = voc()["competitor_board"]
    comp = board[0]["competitor"] if board else None
    prompt = (f"You are a creator-brief strategist for a hair-tool brand. Product: {product}. Winning "
              f"captions: {captions}. Audience buy-intent comments: {intent}. Objections: {objection}. "
              f"Praise: {praise}. Top competitor the audience names: {comp}. Write a tight creative brief "
              f"with 4 short sections — HOOK, PROOF/DEMO, PREEMPT (turn the competitor's weakness into a "
              f"positioning angle), CTA. Ground every line in the data above. (Synthetic data.)")
    try:
        return {"product": product, "brief": _claude(prompt),
                "grounding": {"captions": captions, "intent": intent, "objections": objection, "competitor": comp}}
    except Exception as e:
        return {"note": f"brief unavailable: {str(e)[:120]}"}


def explain(verdict, handle=None, video=None, campaign=None):
    """Ground a decision-queue verdict in the relevant audience comments (the 'why?' button)."""
    if not os.getenv("ANTHROPIC_API_KEY"):
        return _no_key()
    cm = _comments()
    if handle:
        rel = cm[cm["handle"].str.lower() == str(handle).lower()]
    elif video:
        rel = cm[cm["video_id"] == video]
    else:
        rel = cm.head(8)
    quotes = rel["comment_text"].drop_duplicates().head(8).tolist()
    prompt = (f"A creator-sampling decision engine gave this verdict: '{verdict}'. Here are real audience "
              f"comments for that target: {quotes}. In 2-3 sentences, explain how these comments support "
              f"or complicate the verdict. Be specific and grounded. (Synthetic data.)")
    try:
        return {"answer": _claude(prompt, 300), "quotes": quotes}
    except Exception as e:
        return {"note": f"explain unavailable: {str(e)[:120]}"}


def query(question):
    """Agentic hybrid query — one question across comments + video content + campaign verdicts."""
    if not os.getenv("ANTHROPIC_API_KEY"):
        return _no_key()
    cm = _comments()
    vids = pd.read_csv(CONTRACT["videos"])
    camps = pd.read_csv(CONTRACT["campaigns"])
    words = [w for w in str(question).lower().split() if len(w) > 3]
    pat = "|".join(words) if words else "xxxxx"
    ccom = cm[cm["comment_text"].str.lower().str.contains(pat, na=False, regex=True)]["comment_text"].drop_duplicates().head(8).tolist()
    cvid = vids[vids["title"].str.lower().str.contains(pat, na=False, regex=True)]["title"].head(5).tolist()
    ccamp = camps[["campaign_name", "roas", "target_roas"]].head(8).to_dict("records")
    context = f"COMMENTS: {ccom}\nVIDEO TITLES: {cvid}\nCAMPAIGNS (name/roas/target): {ccamp}"
    prompt = (f"Answer the question using ONLY this evidence from three sources (comments, videos, "
              f"campaigns). Cite which source each claim comes from. If the evidence is thin, say so.\n\n"
              f"{context}\n\nQuestion: {question}")
    try:
        return {"answer": _claude(prompt, 500),
                "sources": {"comments": len(ccom), "videos": len(cvid), "campaigns": len(ccamp)}}
    except Exception as e:
        return {"note": f"query unavailable: {str(e)[:120]}"}
