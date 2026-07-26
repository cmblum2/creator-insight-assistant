CHROMA_DIR = "chroma_store"
# Cheap+strong. Swap to "claude-haiku-4-5-20251001" to cut cost, or "claude-opus-4-8" for max quality.
ANSWER_MODEL = "claude-sonnet-5"

INGEST_CONFIG = {   # matches the synthetic files from scripts/gen_data.py
    "creators": {"path": "data/creators.csv",
                 "text_cols": ["handle", "category", "bio"],
                 "meta_cols": ["handle", "category"]},
    "comments": {"path": "data/comments.csv",
                 "text_cols": ["comment_text"],
                 "meta_cols": ["handle", "creator_id", "video_id"]},
}
