import os

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from app.graph import APP

api = FastAPI(title="Creator Insight Assistant")


class Q(BaseModel):
    question: str
    intent_only: bool = False


@api.get("/health")
def health():
    return {"ok": True}


@api.get("/recommend")
def recs(product: str = "", n: int = 10):
    from app.recommend import recommend
    return recommend(product=product, n=min(max(n, 1), 50))


@api.post("/ask")
def ask(q: Q):
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise HTTPException(503, "ANTHROPIC_API_KEY is not set on the server")
    out = APP.invoke({"question": q.question, "intent_only": q.intent_only})
    return {"answer": out["answer"],
            "sources": [c["meta"] for c in out["contexts"]]}


# static chat UI at /
api.mount("/", StaticFiles(directory="static", html=True), name="ui")
