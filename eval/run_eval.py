"""RAGAS eval harness. Runs each eval question through the graph, scores retrieval + answer.

- Judge LLM: Claude via langchain-anthropic (RAGAS defaults to OpenAI; we override so the
  whole project runs on a single ANTHROPIC_API_KEY).
- Embeddings for answer_relevancy: Chroma's local ONNX MiniLM — the same model used for
  retrieval, so the eval sees the index the way the retriever does. No embeddings API key.
- Also reports a free, non-LLM "retrieval hit rate": fraction of questions where at least one
  retrieved context contains one of the question's must_contain terms.

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
from ragas.metrics import faithfulness, answer_relevancy

from app.config import JUDGE_MODEL
from app.graph import APP

# context_precision classically needs a ground-truth reference answer; our eval set is
# question-only, so use the reference-free variant (same idea, judged against the answer).
from ragas.metrics import ContextUtilization

context_metric = ContextUtilization()


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
        contexts = [c["text"] for c in out["contexts"]]
        rows.append({"question": q, "answer": out["answer"], "contexts": contexts})
        terms = [t.lower() for t in case.get("must_contain", [])]
        if terms:
            hit_den += 1
            joined = " ".join(contexts).lower()
            hit_num += any(t in joined for t in terms)
        print(f"answered: {q}")

    judge = LangchainLLMWrapper(ChatAnthropic(model=JUDGE_MODEL, temperature=0, max_tokens=1024))
    emb = LangchainEmbeddingsWrapper(LocalMiniLMEmbeddings())
    res = evaluate(Dataset.from_list(rows),
                   metrics=[faithfulness, answer_relevancy, context_metric],
                   llm=judge, embeddings=emb)

    hit_rate = hit_num / hit_den if hit_den else float("nan")
    per_q = None
    if hasattr(res, "to_pandas"):
        df = res.to_pandas()
        qcol = "user_input" if "user_input" in df.columns else "question"
        cols = [qcol] + [m.name for m in (faithfulness, answer_relevancy, context_metric)
                         if m.name in df.columns]
        per_q = df[cols]

    with open("eval/report.md", "w", encoding="utf-8") as f:
        f.write("# RAG eval report\n\n")
        f.write(f"- Questions: {len(rows)}\n")
        f.write(f"- Retrieval hit rate (must_contain term in retrieved contexts): "
                f"{hit_num}/{hit_den} = {hit_rate:.2f}\n")
        f.write(f"- RAGAS: {res}\n")
        if per_q is not None:
            f.write("\n## Per-question scores\n\n")
            f.write(per_q.to_markdown(index=False))
            f.write("\n")
    print(res)
    print(f"retrieval hit rate: {hit_num}/{hit_den} = {hit_rate:.2f}")
    print("wrote eval/report.md")


if __name__ == "__main__":
    main()
