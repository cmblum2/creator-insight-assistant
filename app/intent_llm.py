"""LLM-based intent + sarcasm classifier — the sarcasm-aware upgrade over the regex buy-intent filter.

The regex (app/intent.py) is cheap and free but takes text literally, so it counts sarcastic comments
("oh sure, let me add to cart another $40 brush I don't need") as genuine buy-intent. This uses Claude
to classify each comment's GENUINE purchase intent AND whether it's sarcastic — which the regex can't
see. eval/eval_sarcasm.py puts a number on the difference.

Design: BATCHED (one API call per chunk, cheap Haiku model) and it GRACEFULLY DEGRADES to the regex if
no ANTHROPIC_API_KEY, so the app still runs free — the LLM is a measured upgrade, not a hard dependency.
"""
import json
import os

from app.config import INTENT_MODEL
from app.intent import buy_intent as _regex_intent

_SYS = ("You classify TikTok Shop comments for a creator-sampling engine. For each comment decide two "
        "things: (1) buy_intent — would a seller count this as a GENUINE purchase-intent signal (real "
        "interest in buying)? (2) sarcastic — is it sarcastic/ironic? A sarcastic comment that mentions "
        "buying, price, or a link is NOT genuine intent. Judge tone, not keywords.")


def _prompt(texts):
    body = "\n".join(f"{i + 1}. {t}" for i, t in enumerate(texts))
    return ('Classify each comment below. Return ONLY a JSON array (no prose) of objects '
            '{"buy_intent": true|false, "sarcastic": true|false}, exactly one per comment, in order.\n\n'
            + body)


def _regex_row(t):
    return {"buy_intent": _regex_intent(t), "sarcastic": None, "source": "regex-fallback"}


def classify_many(texts, model=INTENT_MODEL, chunk=25):
    """Classify a list of comments. Returns a list of {buy_intent, sarcastic, source} aligned to input.
    Falls back to the regex (sarcastic=None) with no key, or per-chunk on any parse/API error."""
    texts = [str(t or "") for t in texts]
    if not texts:
        return []
    if not os.getenv("ANTHROPIC_API_KEY"):
        return [_regex_row(t) for t in texts]
    import anthropic
    client = anthropic.Anthropic()
    out = []
    for i in range(0, len(texts), chunk):
        batch = texts[i:i + chunk]
        try:
            msg = client.messages.create(model=model, max_tokens=2000, system=_SYS,
                                          messages=[{"role": "user", "content": _prompt(batch)}])
            txt = "".join(b.text for b in msg.content if b.type == "text")
            arr = json.loads(txt[txt.index("["):txt.rindex("]") + 1])
            if len(arr) != len(batch):
                raise ValueError("length mismatch")
            for o in arr:
                out.append({"buy_intent": bool(o.get("buy_intent")),
                            "sarcastic": bool(o.get("sarcastic")), "source": "llm"})
        except Exception:
            out.extend(_regex_row(t) | {"source": "regex-fallback-error"} for t in batch)
    return out


def classify(text):
    """Single comment -> {buy_intent, sarcastic, source}."""
    return classify_many([text])[0]
