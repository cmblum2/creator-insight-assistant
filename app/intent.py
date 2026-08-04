"""Buy-intent lexicon (v2) — a cheap, transparent regex classifier over comment text.

v2 fixes three failure modes v1 had in production (all now covered by tests/test_intent_lexicon.py):
  1. second-person advice matched intent  ("you need to get a brush for her")  → intent now needs a
     FIRST-PERSON subject.
  2. past purchases filed as buying-now    ("...after I just bought one")        → a separate
     confirmed-purchase category, checked BEFORE buying-now.
  3. praise words reported as interest     ("obsessed", "so cute")               → praise is its own
     low category; "obsessed" only counts as desire when it has an object ("obsessed with this").

Precedence is first-match-wins, HIGH → MED → LOW. `buy_intent()` stays a bool (it's the model-facing
feature used by the RAG context filter + intent_data — do NOT couple it to the display taxonomy; the
richer `classify_intent()` categories are for display/VoC only).
"""
import re

LEXICON_VERSION = 2

# HIGH — confirmed purchase (checked BEFORE buying-now so "just bought one" isn't mislabeled in-flight)
_CONFIRMED = re.compile(
    r"\b((just|finally|already)\s+(ordered|bought|purchased|copped|grabbed|snagged)"
    r"|(ordered|bought|purchased|copped|got)\s+(mine|one|it|this|these)"
    r"|received\s+(mine|it|today)|on its way|arrived today)\b", re.I)

# HIGH — intent to buy, requires a FIRST-PERSON subject. Two shapes: (a) i/we/i'm + modal + verb,
# (b) contracted imma/ima/finna (already mean "going to") straight to the verb.
_INTENT = re.compile(
    r"\b(i|we|i'?m)\s+(am\s+|are\s+)?"
    r"(gonna|going to|need to|have to|about to|finna|will)\s+(buy|order|get|cop|grab)\b"
    r"|\b(imma|ima|finna)\s+(buy|order|get|cop|grab)\b", re.I)

# MED — buying now / in-flight actions only
_BUYING = re.compile(
    r"\b(add(ing)? to cart|in my cart|check(ing)? out|checkout"
    r"|ordering( this| it| one| now)?|buying (this|it|one|now|these)"
    r"|take my money|where.*(buy|link)|drop the link|link please|restock)\b", re.I)

# LOW — interest (desire with an object) vs praise (sentiment). "obsessed" is desire only with an object.
_INTEREST = re.compile(
    r"\b(want (this|it|these|one|so bad)|need (this|it|these|one)|gimme|omg|so good"
    r"|obsessed with (this|it|these|that))\b", re.I)
_PRAISE = re.compile(
    r"\b(love|obsessed|cute|beautiful|amazing|gorgeous|stunning|pretty|gorg|perfect)\b", re.I)

# categories that a seller would count as a genuine purchase-intent signal
_BUY_CATEGORIES = {"confirmed-purchase", "intent-to-buy", "buying-now"}
_SCORE = {"confirmed-purchase": 90, "intent-to-buy": 80, "buying-now": 70,
          "interest": 25, "praise": 15, "none": 0}


def classify_intent(text):
    """Return {"category", "score", "version"} for one comment. First match wins, HIGH→MED→LOW."""
    t = text or ""
    if _CONFIRMED.search(t):
        cat = "confirmed-purchase"
    elif _INTENT.search(t):
        cat = "intent-to-buy"
    elif _BUYING.search(t):
        cat = "buying-now"
    elif _INTEREST.search(t):
        cat = "interest"
    elif _PRAISE.search(t):
        cat = "praise"
    else:
        cat = "none"
    return {"category": cat, "score": _SCORE[cat], "version": LEXICON_VERSION}


def buy_intent(text: str) -> bool:
    """Model-facing boolean: does a seller count this as a genuine purchase-intent signal?"""
    return classify_intent(text)["category"] in _BUY_CATEGORIES


def rescore(texts):
    """Re-run the current lexicon over a list of raw comment texts (the public twin's stand-in for the
    private engine's `rescore_db --rescore`: here comment categories live in CSVs, not a DB). Returns a
    list of classify_intent() dicts aligned to input — use after bumping LEXICON_VERSION."""
    return [classify_intent(t) for t in texts]
