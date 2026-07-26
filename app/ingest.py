"""CSV -> chunked documents -> Chroma (local sentence-transformers embeddings, no API key)."""
import pandas as pd
import chromadb
from app.config import INGEST_CONFIG, CHROMA_DIR


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

    for s in range(0, len(docs), 500):      # batch to stay under Chroma limits
        col.add(documents=docs[s:s+500], metadatas=metas[s:s+500], ids=ids[s:s+500])
    print(f"indexed {len(docs)} documents into '{CHROMA_DIR}'")


if __name__ == "__main__":
    main()
