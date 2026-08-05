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


def _build_shop(client, slug):
    """Build one shop's RAG collection (corpus_<slug>). CONTRACT resolves to this shop once set_shop
    runs, so INGEST_CONFIG's source keys (creators/comments) read the right dir."""
    from app import tenant
    tenant.set_shop(slug)
    name = f"corpus_{slug}"
    try:
        client.delete_collection(name)   # idempotent re-index
    except Exception:
        pass
    col = client.get_or_create_collection(name)

    docs, metas, ids = [], [], []
    for source, cfg in INGEST_CONFIG.items():
        df = pd.read_csv(CONTRACT[source]).fillna("")   # CONTRACT -> data/shops/<slug>/<source>.csv
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
    print(f"  [{slug}] indexed {len(docs)} documents into '{name}'")
    return len(docs)


def main():
    from app import tenant
    client = chromadb.PersistentClient(path=CHROMA_DIR)
    shops = tenant.list_shops() or [{"slug": tenant.default_shop()}]
    total = sum(_build_shop(client, s["slug"]) for s in shops)
    print(f"indexed {total} documents across {len(shops)} shop(s) into '{CHROMA_DIR}'")


if __name__ == "__main__":
    main()
