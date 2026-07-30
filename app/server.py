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


@api.get("/decisions")
def decisions():
    """Act-today queue: one ranked list across GMV-Max campaigns (scale/cut), spark timing, and
    sampling picks — same verdict logic as production, on synthetic data."""
    from app.decide import decision_queue
    try:
        return decision_queue()
    except Exception as e:
        raise HTTPException(503, f"decision queue unavailable: {str(e)[:200]}")


@api.get("/allocate")
def allocate_endpoint(budget: float = 50000):
    """Budget allocator: split a budget across paid GMV-Max vs organic sampling by marginal profit."""
    from app.allocator import allocate
    try:
        return allocate(min(max(budget, 0), 100_000_000))
    except Exception as e:
        raise HTTPException(503, f"allocator unavailable: {str(e)[:200]}")


@api.get("/post_funnel")
def post_funnel():
    """Sample -> post -> sale funnel: shipped samples, how many became content, how many sold."""
    from app.post_rate import funnel
    try:
        return funnel()
    except Exception as e:
        raise HTTPException(503, f"post funnel unavailable: {str(e)[:200]}")


@api.get("/heterogeneity")
def heterogeneity_endpoint():
    """CATE: which creator segments show the largest sampling treatment effect."""
    from app.heterogeneity import heterogeneity
    try:
        return heterogeneity()
    except Exception as e:
        raise HTTPException(503, f"heterogeneity unavailable: {str(e)[:200]}")


@api.get("/voc")
def voc_endpoint():
    """Voice of Customer: category mix, competitor board, price/praise themes over the comment corpus."""
    from app.voc import voc
    try:
        return voc()
    except Exception as e:
        raise HTTPException(503, f"voc unavailable: {str(e)[:200]}")


@api.get("/voc_actions")
def voc_actions_endpoint():
    """VoC -> ranked action list (validated vs qualitative)."""
    from app.voc import action_list
    try:
        return action_list()
    except Exception as e:
        raise HTTPException(503, f"voc_actions unavailable: {str(e)[:200]}")


@api.get("/voc_narrate")
def voc_narrate_endpoint():
    """LLM positioning read over the VoC boards."""
    from app.voc import narrate
    try:
        return narrate()
    except Exception as e:
        raise HTTPException(503, f"voc narrate unavailable: {str(e)[:200]}")


@api.get("/theme_lift")
def theme_lift_endpoint():
    """Themes -> conversion: comment-theme mix vs video conversion (Bonferroni)."""
    from app.theme_lift import report
    try:
        return report()
    except Exception as e:
        raise HTTPException(503, f"theme_lift unavailable: {str(e)[:200]}")


@api.get("/spark")
def spark_endpoint():
    """Spark timing: ROAS by video age at first spark + organic winners to gate."""
    from app.spark import spark_report
    try:
        return spark_report()
    except Exception as e:
        raise HTTPException(503, f"spark unavailable: {str(e)[:200]}")


@api.get("/classify")
def classify_comment(text: str = ""):
    """Buy-intent + sarcasm on one comment: the regex filter vs the sarcasm-aware LLM classifier,
    side by side. The LLM adds sarcasm (falls back to regex with no API key)."""
    from app.intent import buy_intent
    from app.intent_llm import classify
    return {"text": text, "regex": {"buy_intent": buy_intent(text)}, "llm": classify(text)}


@api.get("/economics")
def economics():
    """Unit economics: ROI, LTV/retention, size-the-prize, sensitivity — revenue turned into profit."""
    from app.economics import unit_economics, size_the_prize, sensitivity
    from app.cohorts import ltv, retention_curve
    try:
        return {"unit_economics": unit_economics(), "size_the_prize": size_the_prize(),
                "sensitivity": sensitivity(), "ltv": ltv(), "retention": retention_curve()}
    except Exception as e:
        raise HTTPException(503, f"economics unavailable: {str(e)[:200]}")


@api.get("/holdout")
def holdout():
    """The controlled test: retrospective natural-experiment readout + forward randomized-ledger status."""
    from app.holdout import report
    try:
        return report()
    except Exception as e:
        raise HTTPException(503, f"holdout unavailable: {str(e)[:200]}")


@api.get("/drift")
def drift():
    """Model-drift monitor: input-feature PSI, causal-skill decay, hit-rate drop vs a saved baseline."""
    from app.drift import drift_report
    try:
        return drift_report()
    except Exception as e:
        raise HTTPException(503, f"drift unavailable: {str(e)[:200]}")


@api.get("/recommender")
def recommender():
    """Recommender scorecard: does the ranking pick winners? rank-IC + precision@K + calibration-by-rank
    over the synthetic outcomes."""
    from app.recommender_eval import recommender_scorecard
    try:
        return recommender_scorecard()
    except Exception as e:
        raise HTTPException(503, f"recommender unavailable: {str(e)[:200]}")


@api.post("/ask")
def ask(q: Q):
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise HTTPException(503, "ANTHROPIC_API_KEY is not set on the server")
    import anthropic
    try:
        out = APP.invoke({"question": q.question, "intent_only": q.intent_only})
    except anthropic.APIStatusError as e:
        # surface billing/auth problems as a clear 503 instead of an opaque 500 —
        # the recommendation engine keeps working either way
        raise HTTPException(503, f"LLM unavailable: {e.body.get('error', {}).get('message', str(e))}"
                            if isinstance(getattr(e, 'body', None), dict) else f"LLM unavailable: {e}")
    return {"answer": out["answer"],
            "sources": [c["meta"] for c in out["contexts"]]}


# static chat UI at /
api.mount("/", StaticFiles(directory="static", html=True), name="ui")
