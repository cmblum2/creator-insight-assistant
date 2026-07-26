import re

# Reuse of the creator-discovery buy-intent idea: a cheap regex signal over comment text.
INTENT = re.compile(
    r"\b(where.*(buy|get)|link|add(ing)? to cart|need this|ordering|"
    r"just (bought|ordered)|sold out|restock|how much|price)\b", re.I)


def buy_intent(text: str) -> bool:
    return bool(INTENT.search(text or ""))
