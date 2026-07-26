CHROMA_DIR = "chroma_store"
# Cheap+strong. Swap to "claude-haiku-4-5-20251001" to cut cost, or "claude-opus-4-8" for max quality.
ANSWER_MODEL = "claude-sonnet-5"
# RAGAS evaluator LLM. Not claude-sonnet-5: the Claude 5 family rejects the `temperature`
# param, and ragas sets it on the judge internally.
JUDGE_MODEL = "claude-sonnet-4-5"

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
