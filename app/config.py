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

# v2 sampling-engine contract tables (synthetic; produced by scripts/gen_data.py).
# creator_insights also feeds the RAG corpus via a custom doc builder in app/ingest.py.
CONTRACT = {
    "comments": "data/comments.csv",
    "creator_insights": "data/creator_insights.csv",
    "roster": "data/roster.csv",
    "seeding_decisions": "data/seeding_decisions.csv",
    "seeding_controls": "data/seeding_controls.csv",
    # v3: synthetic sampling outcomes + order timeline (economics / holdout / drift / cohorts)
    "outcomes": "data/outcomes.csv",
    "orders": "data/orders.csv",
    # v4: warehouse-feature twins (decision queue / allocator / spark / post-funnel / voc / theme-lift)
    "campaigns": "data/campaigns.csv",
    "videos": "data/videos.csv",
    "sample_requests": "data/sample_requests.csv",
    "creator_videos": "data/creator_videos.csv",
    "product_categories": "data/product_categories.csv",
    # v5: monthly cohort series for the weekly agency report's trend desk
    "monthly_trends": "data/monthly_trends.csv",
}

# sample-program unit economics (synthetic, but the same math the real engine uses).
# net contribution margin = product contribution - affiliate commission; sample cost = COGS + ship.
NET_MARGIN = 0.30
SAMPLE_COST = 14.0
PRODUCT_CONTRIB = 0.405
COMMISSION_RATE = 0.105
