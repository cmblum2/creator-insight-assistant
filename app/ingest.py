"""CSV -> chunked documents -> Chroma (local sentence-transformers embeddings, no API key)."""
import json

import pandas as pd
import chromadb
from app.config import CONTRACT, INGEST_CONFIG, CHROMA_DIR


def _fmt(v):
    if v in (None, "", []):
        return None
    if isinstance(v, list):
        return "; ".join(filter(None, (_fmt(x) for x in v)))
    if isinstance(v, dict):
        return ", ".join(f"{k}={_fmt(x)}" for k, x in v.items() if x not in (None, "", []))
    return str(v)


def insight_doc(row):
    """Self-contained doc per (creator, product) scoring insight."""
    try:
        j = json.loads(row["insight_json"])
    except (TypeError, ValueError):
        j = {}
    lines = [f"creator: {j.get('handle', row['creator_id'])} "
             f"(rank #{row['rank_position']}, ordinal)",
             f"suggested product: {row['suggested_product']}"]
    for label, key in [("niche", "niche"), ("followers", "followerCount"),
                       ("engagement rate", "engagementRate"),
                       ("trust-adjusted score", "trustAdjScore"), ("signals", "signals"),
                       ("reasons", "reasons"), ("watchouts", "watchouts"),
                       ("video totals", "videoTotals")]:
        val = _fmt(j.get(key))
        if val is not None:
            lines.append(f"{label}: {val}")
    return "\n".join(lines)


def main():
    client = chromadb.PersistentClient(path=CHROMA_DIR)
    try:
        client.delete_collection("creator_corpus")   # idempotent re-index
    except Exception:
        pass
    col = client.get_or_create_collection("creator_corpus")

    docs, metas, ids = [], [], []
    for source, cfg in INGEST_CONFIG.items():
        df = pd.read_csv(cfg["path"]).fillna("")
        for i, row in df.iterrows():
            text = "\n".join(f"{c}: {row[c]}" for c in cfg["text_cols"]
                             if str(row.get(c, "")).strip())
            if not text.strip():
                continue
            docs.append(text)
            metas.append({"source": source, **{k: str(row.get(k, "")) for k in cfg["meta_cols"]}})
            ids.append(f"{source}-{i}")

    ins = pd.read_csv(CONTRACT["creator_insights"]).fillna("")
    for i, row in ins.iterrows():
        docs.append(insight_doc(row))
        try:
            handle = json.loads(row["insight_json"]).get("handle", "")
        except (TypeError, ValueError):
            handle = ""
        metas.append({"source": "insights", "handle": str(handle),
                      "creator_id": str(row["creator_id"]),
                      "rank_position": str(row["rank_position"]),
                      "suggested_product": str(row["suggested_product"])})
        ids.append(f"insights-{i}")

    for s in range(0, len(docs), 500):      # batch to stay under Chroma limits
        col.add(documents=docs[s:s+500], metadatas=metas[s:s+500], ids=ids[s:s+500])
    print(f"indexed {len(docs)} documents into '{CHROMA_DIR}'")


if __name__ == "__main__":
    main()
