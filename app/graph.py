"""LangGraph: retrieve -> (optional buy-intent filter) -> answer (Claude, grounded + cited)."""
from typing import TypedDict
from langgraph.graph import StateGraph, END
import chromadb
import anthropic
from dotenv import load_dotenv
from app.config import CHROMA_DIR, ANSWER_MODEL
from app.intent import buy_intent

load_dotenv()   # picks up ANTHROPIC_API_KEY from a local .env (gitignored)
_col = chromadb.PersistentClient(path=CHROMA_DIR).get_collection("creator_corpus")
_llm = None     # created lazily so the server (and /health) starts without a key


def _client():
    global _llm
    if _llm is None:
        _llm = anthropic.Anthropic()
    return _llm


class S(TypedDict):
    question: str
    intent_only: bool
    contexts: list
    answer: str


def retrieve(s):
    r = _col.query(query_texts=[s["question"]], n_results=8)
    ctx = [{"text": d, "meta": m} for d, m in zip(r["documents"][0], r["metadatas"][0])]
    if s.get("intent_only"):
        ctx = [c for c in ctx if buy_intent(c["text"])] or ctx
    return {"contexts": ctx}


def answer(s):
    # include the handle from metadata — the raw comment text alone can't tell the model
    # WHO said it, so "which creators..." questions would be unanswerable
    def label(c):
        h = c["meta"].get("handle", "")
        return f"{c['meta'].get('source')}{', ' + h if h else ''}"
    block = "\n\n".join(f"[{i}] ({label(c)}) {c['text']}"
                        for i, c in enumerate(s["contexts"]))
    msg = _client().messages.create(
        model=ANSWER_MODEL, max_tokens=700,
        system=("Answer ONLY from the numbered context. Cite sources like [0],[2]. "
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
