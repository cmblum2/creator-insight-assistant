"""RAGAS eval harness. Runs each eval question through the graph, scores retrieval + answer.
Writes eval/report.md. Requires ANTHROPIC_API_KEY (uses Claude for generation + RAGAS judging)."""
import json
from datasets import Dataset
from ragas import evaluate
from ragas.metrics import faithfulness, answer_relevancy, context_precision
from app.graph import APP


def main():
    rows = []
    for line in open("eval/eval_set.jsonl", encoding="utf-8"):
        q = json.loads(line)["question"]
        out = APP.invoke({"question": q})
        rows.append({"question": q,
                     "answer": out["answer"],
                     "contexts": [c["text"] for c in out["contexts"]]})
    res = evaluate(Dataset.from_list(rows),
                   metrics=[faithfulness, answer_relevancy, context_precision])
    with open("eval/report.md", "w", encoding="utf-8") as f:
        f.write(f"# RAG eval report\n\n{res}\n")
    print(res)


if __name__ == "__main__":
    main()
