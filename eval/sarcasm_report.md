# Sarcasm eval — regex buy-intent vs LLM classifier

Hand-labeled set: **24 comments** (10 sarcastic, all with true buy_intent=false).

| metric | regex | LLM (Claude) |
|---|---|---|
| buy-intent accuracy | 79% | 92% |
| false positives on sarcastic comments | **5/10** | **0/10** |
| sarcasm-detection accuracy | — (no notion of sarcasm) | 100% |

**Finding:** the regex flags **5 of 10** sarcastic comments as genuine buy-intent — it matches keywords ('add to cart', 'how much', 'buy') and can't read tone. The LLM classifier cuts that to **0/10** and detects sarcasm at **100%**. Impact is bounded: buy-intent density is a soft ranking signal — the engine's causal labels come from real GMV/orders, which sarcasm can't fake.

Regex false positives (sarcasm counted as intent):
- "oh sure let me add to cart another $40 brush i definitely need"
- "how much is it? asking so i know exactly how much NOT to spend"
- "where do i even buy this life-changing miracle, gimme a break"
- "just bought mine and by mine i mean the $6 dupe lmao"
- "restock?? so i can keep NOT affording it, cool"
