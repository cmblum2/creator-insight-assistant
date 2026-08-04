"""Regression tests for the v2 intent lexicon — pins the three v1 failure modes + the category splits.
Run: python -m pytest tests/test_intent_lexicon.py   (or just: python tests/test_intent_lexicon.py)
"""
from app.intent import buy_intent, classify_intent, LEXICON_VERSION


def cat(t):
    return classify_intent(t)["category"]


def test_version():
    assert LEXICON_VERSION == 2


# ── v1 failure mode 1: second-person advice must NOT be buy-intent ────────────────────────────
def test_second_person_advice_is_not_intent():
    assert buy_intent("you need to get a wet brush for her") is False
    assert cat("you need to get a wet brush for her") != "intent-to-buy"


def test_first_person_intent_still_fires():
    for t in ["i'm gonna buy this", "i need to get one", "imma order it", "we will grab these"]:
        assert cat(t) == "intent-to-buy", t
        assert buy_intent(t) is True


# ── v1 failure mode 2: past purchase is confirmed-purchase, not buying-now ─────────────────────
def test_past_purchase_is_confirmed_not_buying_now():
    assert cat("obsessed after i just bought one") == "confirmed-purchase"
    assert cat("ordered mine last week") == "confirmed-purchase"
    assert cat("it arrived today and i love it") == "confirmed-purchase"


def test_buying_now_is_inflight_only():
    assert cat("adding to cart now") == "buying-now"
    assert cat("where do i buy this") == "buying-now"
    assert buy_intent("take my money") is True


# ── v1 failure mode 3: praise words are praise, not interest ───────────────────────────────────
def test_praise_is_not_interest():
    for t in ["so cute", "obsessed", "gorgeous", "love this"]:
        assert cat(t) == "praise", t
        assert buy_intent(t) is False


def test_obsessed_needs_object_to_be_interest():
    assert cat("obsessed") == "praise"
    assert cat("obsessed with this") == "interest"


def test_interest_is_low_not_buy():
    assert cat("want this so bad") == "interest"
    assert buy_intent("want this so bad") is False


if __name__ == "__main__":
    import traceback
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"PASS {fn.__name__}")
        except AssertionError:
            failed += 1
            print(f"FAIL {fn.__name__}")
            traceback.print_exc()
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    raise SystemExit(1 if failed else 0)
