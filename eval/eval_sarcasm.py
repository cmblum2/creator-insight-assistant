"""Sarcasm eval — put a NUMBER on the regex buy-intent filter's blind spot, and the LLM's fix.

Runs both classifiers over a hand-labeled set (eval/sarcasm_set.jsonl) and reports:
  * buy-intent accuracy — regex vs LLM
  * the headline: FALSE-POSITIVE rate on SARCASTIC comments (how often each says "buy intent" when a
    sarcastic comment truly has none) — this is the exact failure the regex can't avoid
  * sarcasm-detection accuracy (LLM only; the regex has no notion of sarcasm)

Free tier: with no ANTHROPIC_API_KEY the LLM path falls back to the regex and its columns read
"n/a (no key)" — the regex numbers still stand. Mirrors the RAGAS harness: labeled set -> metrics ->
a documented failure case.

    python -m eval.eval_sarcasm
"""
import json
import os

from app.intent import buy_intent as regex_intent
from app.intent_llm import classify_many


def _load():
    rows = []
    with open("eval/sarcasm_set.jsonl", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def run():
    rows = _load()
    texts = [r["text"] for r in rows]
    have_key = bool(os.getenv("ANTHROPIC_API_KEY"))
    preds = classify_many(texts)
    llm_ok = have_key and any(p["source"] == "llm" for p in preds)

    n = len(rows)
    sar = [r for r in rows if r["sarcastic"]]
    regex_acc = sum(regex_intent(r["text"]) == r["buy_intent"] for r in rows) / n
    # false positives specifically on sarcastic comments (all truly have buy_intent=False)
    regex_sar_fp = sum(regex_intent(r["text"]) for r in sar)
    llm_acc = sum(p["buy_intent"] == r["buy_intent"] for p, r in zip(preds, rows)) / n if llm_ok else None
    llm_sar_fp = sum(p["buy_intent"] for p, r in zip(preds, rows) if r["sarcastic"]) if llm_ok else None
    sar_detect = (sum((p["sarcastic"] is not None) and (p["sarcastic"] == r["sarcastic"])
                      for p, r in zip(preds, rows)) / n) if llm_ok else None

    L = ["# Sarcasm eval — regex buy-intent vs LLM classifier\n",
         f"Hand-labeled set: **{n} comments** ({len(sar)} sarcastic, all with true buy_intent=false).\n",
         "| metric | regex | LLM (Claude) |",
         "|---|---|---|",
         f"| buy-intent accuracy | {regex_acc:.0%} | {f'{llm_acc:.0%}' if llm_ok else 'n/a (no key)'} |",
         f"| false positives on sarcastic comments | **{regex_sar_fp}/{len(sar)}** | "
         f"{f'**{llm_sar_fp}/{len(sar)}**' if llm_ok else 'n/a (no key)'} |",
         f"| sarcasm-detection accuracy | — (no notion of sarcasm) | "
         f"{f'{sar_detect:.0%}' if llm_ok else 'n/a (no key)'} |",
         "",
         f"**Finding:** the regex flags **{regex_sar_fp} of {len(sar)}** sarcastic comments as genuine "
         f"buy-intent — it matches keywords ('add to cart', 'how much', 'buy') and can't read tone. "
         + (f"The LLM classifier cuts that to **{llm_sar_fp}/{len(sar)}** and detects sarcasm at "
            f"**{sar_detect:.0%}**." if llm_ok
            else "Set ANTHROPIC_API_KEY to score the LLM classifier (Haiku).")
         + " Impact is bounded: buy-intent density is a soft ranking signal — the engine's causal "
           "labels come from real GMV/orders, which sarcasm can't fake.\n"]

    # per-comment misses (regex false positives on sarcasm) for the writeup
    miss = [r["text"] for r in sar if regex_intent(r["text"])]
    if miss:
        L.append("Regex false positives (sarcasm counted as intent):")
        L += [f"- \"{t}\"" for t in miss]

    report = "\n".join(L)
    with open("eval/sarcasm_report.md", "w", encoding="utf-8") as f:
        f.write(report + "\n")
    print(report)
    print(f"\nwrote eval/sarcasm_report.md")


if __name__ == "__main__":
    run()
