"""RAGAS eval harness. Runs each eval question through the graph, scores retrieval + answer.

- Judge LLM: Claude via langchain-anthropic (RAGAS defaults to OpenAI; we override so the
  whole project runs on a single ANTHROPIC_API_KEY).
- Embeddings for answer_relevancy: Chroma's local ONNX MiniLM — the same model used for
  retrieval, so the eval sees the index the way the retriever does. No embeddings API key.
- Four RAGAS metrics — the standard RAG quad — split into ANSWER quality and RETRIEVAL quality:
    answer:    faithfulness (answer grounded in retrieved context), answer_relevancy
    retrieval: context_precision (are the relevant contexts ranked at the top?),
               context_recall   (did retrieval fetch ALL the context the answer needs?)
  The two retrieval metrics are the reason this harness exists: an answer can look good while
  retrieval quietly drops half the relevant evidence — recall is what catches that, and it
  needs a ground-truth `reference` (authored in eval_set.jsonl, grounded in the synthetic corpus).
- Also reports a free, non-LLM "lexical retrieval recall": fraction of questions where a
  retrieved context contains one of the question's must_contain terms (a cheap recall sanity check
  that needs no judge — complements the LLM-judged context_recall).

Writes eval/report.md. Requires ANTHROPIC_API_KEY.
"""
import json

from chromadb.utils.embedding_functions import DefaultEmbeddingFunction
from datasets import Dataset
from langchain_anthropic import ChatAnthropic
from langchain_core.embeddings import Embeddings
from ragas import evaluate
from ragas.embeddings import LangchainEmbeddingsWrapper
from ragas.llms import LangchainLLMWrapper
# The RAG quad. context_precision/context_recall are reference-based (need `reference`); now that
# eval_set.jsonl carries a ground-truth reference per question we use the reference-based precision
# instead of the older reference-free ContextUtilization — precision and recall on the same truth.
from ragas.metrics import faithfulness, answer_relevancy, context_precision, context_recall

from app.config import JUDGE_MODEL
from app.graph import APP

METRICS = [faithfulness, answer_relevancy, context_precision, context_recall]


class LocalMiniLMEmbeddings(Embeddings):
    """LangChain-compatible wrapper around Chroma's default local ONNX embedder."""

    def __init__(self):
        self._ef = DefaultEmbeddingFunction()

    def embed_documents(self, texts):
        return [[float(x) for x in vec] for vec in self._ef(list(texts))]

    def embed_query(self, text):
        return self.embed_documents([text])[0]


def main():
    cases, rows = [], []
    for line in open("eval/eval_set.jsonl", encoding="utf-8"):
        cases.append(json.loads(line))

    hit_num = hit_den = 0
    for case in cases:
        q = case["question"]
        out = APP.invoke({"question": q})
        # judge must see EXACTLY what the answer model saw — including the joined quant-facts
        # line — or correct answers get scored as hallucinations (v1's lesson, re-learned in v2)
        contexts = [f"{c['text']}\n{c['fact_line']}" for c in out["contexts"]]
        rows.append({"question": q, "answer": out["answer"], "contexts": contexts,
                     "reference": case.get("reference", "")})
        terms = [t.lower() for t in case.get("must_contain", [])]
        if terms:
            hit_den += 1
            joined = " ".join(contexts).lower()
            hit_num += any(t in joined for t in terms)
        print(f"answered: {q}")

    # max_tokens must be generous: context_recall/precision decompose the reference into claims
    # and emit per-claim reasoning; at 1024 the judge truncated mid-verdict (LLMDidNotFinishException)
    # and those jobs scored as failures, deflating recall. 4096 gives the judge room to finish.
    judge = LangchainLLMWrapper(ChatAnthropic(model=JUDGE_MODEL, temperature=0, max_tokens=4096))
    emb = LangchainEmbeddingsWrapper(LocalMiniLMEmbeddings())
    res = evaluate(Dataset.from_list(rows), metrics=METRICS, llm=judge, embeddings=emb)

    hit_rate = hit_num / hit_den if hit_den else float("nan")
    per_q = None
    if hasattr(res, "to_pandas"):
        df = res.to_pandas()
        qcol = "user_input" if "user_input" in df.columns else "question"
        cols = [qcol] + [m.name for m in METRICS if m.name in df.columns]
        per_q = df[cols]

    with open("eval/report.md", "w", encoding="utf-8") as f:
        f.write("# RAG eval report\n\n")
        f.write(f"- Questions: {len(rows)}\n")
        f.write("- **Answer quality:** faithfulness, answer_relevancy\n")
        f.write("- **Retrieval quality:** context_precision (relevant contexts ranked high), "
                "context_recall (all needed context retrieved) — both vs. an authored ground truth\n")
        f.write(f"- Lexical retrieval recall (free, non-LLM — must_contain term present in "
                f"retrieved contexts): {hit_num}/{hit_den} = {hit_rate:.2f}\n")
        f.write(f"- RAGAS: {res}\n")
        if per_q is not None:
            f.write("\n## Per-question scores\n\n")
            try:
                f.write(per_q.to_markdown(index=False))
            except ImportError:      # tabulate not installed
                f.write("```\n" + per_q.to_string(index=False) + "\n```")
            f.write("\n")
    print(res)
    print(f"lexical retrieval recall: {hit_num}/{hit_den} = {hit_rate:.2f}")
    print("wrote eval/report.md")


if __name__ == "__main__":
    main()
