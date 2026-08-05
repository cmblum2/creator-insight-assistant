CHROMA_DIR = "chroma_store"
# Cheap+strong. Swap to "claude-haiku-4-5-20251001" to cut cost, or "claude-opus-4-8" for max quality.
ANSWER_MODEL = "claude-sonnet-5"
# RAGAS evaluator LLM. Not claude-sonnet-5: the Claude 5 family rejects the `temperature`
# param, and ragas sets it on the judge internally.
JUDGE_MODEL = "claude-sonnet-4-5"
# Cheap, fast model for the LLM buy-intent + sarcasm classifier (app/intent_llm.py). Classification
# is easy; Haiku is plenty and keeps the sarcasm-aware pass affordable at comment scale.
INTENT_MODEL = "claude-haiku-4-5-20251001"

INGEST_CONFIG = {   # matches the synthetic files from scripts/gen_data.py
    "creators": {"path": "data/creators.csv",
                 "text_cols": ["handle", "category", "bio"],
                 "meta_cols": ["handle", "category"]},
    # handle is IN the text on purpose: documents must be self-contained. The answer prompt
    # and the RAGAS eval both consume document text — if attribution only lives in metadata,
    # correct "which creators..." answers get judged as hallucinations (faithfulness 0).
    "comments": {"path": "data/comments.csv",
                 "text_cols": ["handle", "comment_text"],
                 "meta_cols": ["handle", "creator_id", "video_id"]},
}

# v2–v5 sampling-engine contract tables (synthetic; produced by scripts/gen_data.py).
# MULTI-TENANT: CONTRACT[key] resolves to the CURRENT shop's data dir (data/shops/<slug>/<key>.csv) via
# the request-scoped contextvar in app.tenant — so every data module reads the right shop with no change
# to its own code. creator_insights also feeds the per-shop RAG corpus (app/ingest.py).
_CONTRACT_KEYS = {
    "creators", "comments", "creator_insights", "roster", "seeding_decisions", "seeding_controls",
    "outcomes", "orders", "campaigns", "videos", "sample_requests", "creator_videos",
    "product_categories", "monthly_trends",
}


class _Contract:
    """A shop-aware mapping: CONTRACT['comments'] -> 'data/shops/<current_shop>/comments.csv'."""

    def __getitem__(self, key):
        if key not in _CONTRACT_KEYS:
            raise KeyError(key)
        from app.tenant import shop_dir
        return f"{shop_dir()}/{key}.csv"

    def __contains__(self, key):
        return key in _CONTRACT_KEYS

    def get(self, key, default=None):
        return self[key] if key in _CONTRACT_KEYS else default

    def keys(self):
        return set(_CONTRACT_KEYS)


CONTRACT = _Contract()

# sample-program unit economics (synthetic, but the same math the real engine uses).
# net contribution margin = product contribution - affiliate commission; sample cost = COGS + ship.
NET_MARGIN = 0.30
SAMPLE_COST = 14.0
PRODUCT_CONTRIB = 0.405
COMMISSION_RATE = 0.105
