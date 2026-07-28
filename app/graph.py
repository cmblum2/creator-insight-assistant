"""LangGraph: retrieve (MMR, diversity-aware) -> (optional buy-intent filter) -> answer."""
from typing import TypedDict
from langgraph.graph import StateGraph, END
import chromadb
from chromadb.utils.embedding_functions import DefaultEmbeddingFunction
import numpy as np
import anthropic
from dotenv import load_dotenv
from app.config import CHROMA_DIR, ANSWER_MODEL
from app.intent import buy_intent

load_dotenv()   # picks up ANTHROPIC_API_KEY from a local .env (gitignored)
_col = chromadb.PersistentClient(path=CHROMA_DIR).get_collection("creator_corpus")
_ef = DefaultEmbeddingFunction()   # same local ONNX MiniLM the index was built with
_llm = None     # created lazily so the server (and /health) starts without a key

N_RESULTS = 8    # contexts handed to the answerer
FETCH_K = 40     # candidate pool MMR diversifies over (must be >> N_RESULTS)
MMR_LAMBDA = 0.5  # relevance<->diversity trade-off (1.0 = pure similarity, 0.0 = pure diversity)


def _client():
    global _llm
    if _llm is None:
        _llm = anthropic.Anthropic()
    return _llm


def _cos(a, B):
    a = a / (np.linalg.norm(a) + 1e-9)
    B = B / (np.linalg.norm(B, axis=1, keepdims=True) + 1e-9)
    return B @ a


def _mmr(query_vec, cand_vecs, k, lam=MMR_LAMBDA):
    """Maximal Marginal Relevance: pick k candidates that are each relevant to the query yet
    dissimilar to those already chosen. Fixes redundant retrieval (8 near-duplicate neighbors)
    that tanks context_recall — the retriever must COVER the answer, not just top-match it."""
    sim_q = _cos(query_vec, cand_vecs)
    selected = []
    remaining = list(range(len(cand_vecs)))
    while remaining and len(selected) < k:
        if not selected:
            i = max(remaining, key=lambda j: sim_q[j])
        else:
            chosen = cand_vecs[selected]
            i = max(remaining, key=lambda j: lam * sim_q[j]
                    - (1 - lam) * float(np.max(_cos(cand_vecs[j], chosen))))
        selected.append(i)
        remaining.remove(i)
    return selected


class S(TypedDict):
    question: str
    intent_only: bool
    contexts: list
    answer: str


def retrieve(s):
    from app.enrich import enrich, fact_line
    # over-fetch a candidate pool WITH embeddings, then MMR-select a diverse top-N
    r = _col.query(query_texts=[s["question"]], n_results=FETCH_K,
                   include=["documents", "metadatas", "embeddings"])
    docs, metas, embs = r["documents"][0], r["metadatas"][0], np.array(r["embeddings"][0])
    qv = np.array(_ef([s["question"]])[0])
    order = _mmr(qv, embs, N_RESULTS) if len(embs) else list(range(len(docs)))
    ctx = []
    for j in order:
        m = metas[j]
        e = enrich(m.get("creator_id", ""))
        ctx.append({"text": docs[j], "meta": m, "facts": e, "fact_line": fact_line(e)})
    if s.get("intent_only"):
        ctx = [c for c in ctx if buy_intent(c["text"])] or ctx
    return {"contexts": ctx}


def answer(s):
    # include the handle from metadata — the raw comment text alone can't tell the model
    # WHO said it, so "which creators..." questions would be unanswerable
    def label(c):
        h = c["meta"].get("handle", "")
        return f"{c['meta'].get('source')}{', ' + h if h else ''}"
    block = "\n\n".join(f"[{i}] ({label(c)}) {c['text']}\n{c['fact_line']}"
                        for i, c in enumerate(s["contexts"]))
    msg = _client().messages.create(
        model=ANSWER_MODEL, max_tokens=700,
        system=("Answer ONLY from the numbered context. Cite sources like [0],[2]. "
                "Ranks are ORDINAL — compare order, never treat scores as spend sizes. "
                "Never recommend sampling a creator marked MATCHED CONTROL or ALREADY "
                "SEEDED unless the question asks about them. "
                "If the context doesn't answer it, say so — do not invent creators or quotes."),
        messages=[{"role": "user",
                   "content": f"Context:\n{block}\n\nQuestion: {s['question']}"}])
    # content[0] isn't always text — Claude 5 models may emit a thinking block first
    return {"answer": "".join(b.text for b in msg.content if b.type == "text")}


_g = StateGraph(S)
_g.add_node("retrieve", retrieve)
_g.add_node("answer", answer)
_g.set_entry_point("retrieve")
_g.add_edge("retrieve", "answer")
_g.add_edge("answer", END)
APP = _g.compile()
