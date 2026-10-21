"""Prepare, index, and search scoped document evidence (Pinecone Python SDK v10)."""

import argparse
import json
import os
import sqlite3
from contextlib import closing
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv

try:
    from .analytics import ROOT
    from .reporting import runtime_date, latest_completed_week
    from .runtime_data import active_data_dir
    from .documents import DIMENSIONS, MODEL, digest, prepare_documents
except ImportError:  # Support running this file directly from the repository root.
    from analytics import ROOT
    from reporting import runtime_date, latest_completed_week
    from runtime_data import active_data_dir
    from documents import DIMENSIONS, MODEL, digest, prepare_documents


def settings():
    load_dotenv(ROOT / ".env", override=False)
    missing = [key for key in ("OPENAI_API_KEY", "PINECONE_API_KEY") if not os.getenv(key, "").strip()]
    if missing:
        raise ValueError("Set these keys in the local .env file: " + ", ".join(missing))
    return {"name": os.getenv("PINECONE_INDEX_NAME", "center-performance-copilot"),
            "cloud": os.getenv("PINECONE_CLOUD", "aws"),
            "region": os.getenv("PINECONE_REGION", "us-east-1")}


def open_clients(config, create=False):
    from openai import OpenAI
    from pinecone import Pinecone

    pc = Pinecone()
    if create and not pc.indexes.exists(config["name"]):
        pc.indexes.create(name=config["name"],
                          schema={"fields": {"embedding": {"type": "dense_vector", "dimension": DIMENSIONS,
                                                            "metric": "cosine"}}},
                          deployment={"deployment_type": "managed", "cloud": config["cloud"],
                                      "region": config["region"]}, timeout=60)
    description = pc.indexes.describe(config["name"])
    # Fail before embedding expenditure if this is a legacy or incompatible index.
    raw = description.to_dict()
    field = raw.get("schema", {}).get("fields", {}).get("embedding", {})
    if (field.get("type") != "dense_vector" or field.get("dimension") != DIMENSIONS
            or field.get("metric") != "cosine"):
        raise ValueError("Use a schema-based Pinecone index with an embedding field: 1536 dimensions, cosine")
    if not description.status.ready:
        raise ValueError("Pinecone index is not ready; retry after provisioning completes")
    return OpenAI(timeout=60, max_retries=2), pc.index(config["name"])


def embed_cached(client, cache, texts):
    cache.execute("CREATE TABLE IF NOT EXISTS embeddings (cache_key TEXT PRIMARY KEY, vector TEXT NOT NULL)")
    keys = [digest(f"{MODEL}:{DIMENSIONS}:{text}") for text in texts]
    vectors = [None] * len(texts)
    missing = []
    for i, key in enumerate(keys):
        row = cache.execute("SELECT vector FROM embeddings WHERE cache_key=?", (key,)).fetchone()
        if row:
            vectors[i] = json.loads(row[0])
        else:
            missing.append(i)
    if missing:
        response = client.embeddings.create(model=MODEL, dimensions=DIMENSIONS, encoding_format="float",
                                             input=[texts[i] for i in missing])
        if len(response.data) != len(missing):
            raise ValueError("Embedding API returned an unexpected number of vectors")
        for item in response.data:
            i = missing[item.index]
            if len(item.embedding) != DIMENSIONS:
                raise ValueError("Embedding dimensions do not match the index")
            vectors[i] = item.embedding
            cache.execute("INSERT OR REPLACE INTO embeddings VALUES (?, ?)", (keys[i], json.dumps(item.embedding)))
        cache.commit()
    return vectors


def index_documents(data_dir, create=False):
    data_dir = Path(data_dir) if data_dir is not None else active_data_dir()
    config = settings()
    print("Preparing document chunks...", flush=True)
    plan, chunks = prepare_documents(data_dir)
    print(f"Prepared {len(chunks)} chunks. Loading API libraries and checking Pinecone...", flush=True)
    client, index = open_clients(config, create=create)
    print("Pinecone is ready. Starting embedding and upload batches...", flush=True)
    folder = Path(data_dir) / "retrieval"
    with closing(sqlite3.connect(folder / "embedding_cache.sqlite")) as cache:
        for offset in range(0, len(chunks), 64):
            batch = chunks[offset:offset + 64]
            vectors = embed_cached(client, cache, [c["fields"]["text"] for c in batch])
            index.documents.upsert(namespace=plan["namespace"], documents=[
                {"_id": c["id"], "embedding": vector, **c["fields"]} for c, vector in zip(batch, vectors)])
            print(f"Uploaded {min(offset + 64, len(chunks))}/{len(chunks)} chunks", flush=True)
    # Publish locally only after every upsert succeeds. Each changed snapshot uses a
    # different namespace, preventing removed documents from leaking into new searches.
    state = {**plan, "index_name": config["name"], "indexed_at_utc": datetime.now(timezone.utc).isoformat()}
    temporary = folder / "index_state.tmp"
    temporary.write_text(json.dumps(state, indent=2), encoding="utf-8")
    temporary.replace(folder / "index_state.json")
    print("Indexing complete. Pinecone search visibility may lag briefly behind writes.")
    return state


def evidence_filter(assigned_center, week_start):
    start = date.fromisoformat(week_start)
    if start.weekday() != 6 or start + timedelta(days=6) >= runtime_date():
        raise ValueError("Select a completed Sunday-Saturday reporting week")
    # Guidance must be applicable for the whole week; midweek changes need a future
    # per-day policy lookup rather than silently selecting one version.
    return {"$or": [
        {"$and": [{"scope": {"$eq": assigned_center}}, {"document_type": {"$eq": "weekly_report"}},
                   {"week_start": {"$eq": week_start}}]},
        {"$and": [{"scope": {"$eq": "shared"}}, {"document_type": {"$eq": "guidance"}},
                   {"effective_from": {"$lte": start.toordinal()}},
                   {"effective_to": {"$gte": (start + timedelta(days=6)).toordinal()}}]},
    ]}


def select_evidence(reports, guidance, top_k):
    """Reserve evidence slots for operating context and shared guidance."""
    reports = sorted(reports, key=lambda m: m.get("section") != "Director observations")
    report_slots = top_k // 2
    selected = reports[:report_slots] + guidance[:top_k - report_slots]
    seen = {m["chunk_id"] for m in selected}
    for match in reports + guidance:
        if len(selected) >= top_k:
            break
        if match["chunk_id"] not in seen:
            selected.append(match)
            seen.add(match["chunk_id"])
    return selected


class CenterDocumentSearch:
    """Bind assigned_center from trusted identity; agent input cannot override it."""

    def __init__(self, data_dir, assigned_center):
        self.data_dir = Path(data_dir).resolve() if data_dir is not None else active_data_dir()
        self.assigned_center = assigned_center
        with closing(sqlite3.connect((self.data_dir / "center_performance.sqlite").as_uri() + "?mode=ro", uri=True)) as conn:
            if conn.execute("SELECT 1 FROM centers WHERE center_id=?", (assigned_center,)).fetchone() is None:
                raise ValueError("Assigned center does not exist")

    def search(self, question, week_start=None, top_k=6):
        week_start = week_start or str(latest_completed_week())
        if not question.strip() or not 1 <= top_k <= 20:
            raise ValueError("Supply a non-empty question and top_k between 1 and 20")
        filters = evidence_filter(self.assigned_center, week_start)
        folder = self.data_dir / "retrieval"
        state_path = folder / "index_state.json"
        if not state_path.exists():
            raise ValueError("No completed index run found; run retrieval.py index first")
        state = json.loads(state_path.read_text(encoding="utf-8"))
        if state["model"] != MODEL or state["dimensions"] != DIMENSIONS:
            raise ValueError("Indexed model settings differ; reindex before searching")
        config = settings()
        if config["name"] != state["index_name"]:
            raise ValueError("Configured index differs from the completed index run")
        client, index = open_clients(config)
        from pinecone import DenseVectorQuery

        def query(vector, filter_value):
            response = index.documents.search(namespace=state["namespace"], top_k=top_k,
                score_by=[DenseVectorQuery(field="embedding", values=vector)], filter=filter_value,
                include_fields=["text", "title", "source_path", "section", "document_id", "scope", "week_start", "version"])
            return [{"chunk_id": m.id, "score": m.score,
                     **{k: v for k, v in m.to_dict().items() if not k.startswith("_")}} for m in response.matches]

        with closing(sqlite3.connect(folder / "embedding_cache.sqlite")) as cache:
            vector = embed_cached(client, cache, [question])[0]
            if top_k == 1:
                matches = query(vector, filters)
            else:
                reports = query(vector, filters["$or"][0])
                observations = next((m["text"] for m in reports if m.get("section") == "Director observations"), "")
                guide_question = question + ("\nRelevant center operating observations:\n" + observations if observations else "")
                guide_vector = embed_cached(client, cache, [guide_question])[0]
                guidance = query(guide_vector, filters["$or"][1])
                matches = select_evidence(reports, guidance, top_k)
        # Similarity is not a calibrated confidence score. The answering agent must
        # check evidence support and acknowledge gaps, even when matches exist.
        return {"center_id": self.assigned_center, "week_start": week_start,
                "indexed_at_utc": state["indexed_at_utc"], "matches": matches,
                "retrieval_method": "report_and_contextual_guidance" if top_k > 1 else "dense",
                "note": "Separate report and guidance searches reserve evidence slots. Scores from different queries are not comparable confidence probabilities; check passage support."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, help="Defaults to the current rolling dataset")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("prepare", help="Local chunking only; no keys or API calls")
    indexing = commands.add_parser("index", help="Embed and upload; requires keys and uses API credits")
    indexing.add_argument("--create-index", action="store_true", help="Create the configured Pinecone index if absent")
    searching = commands.add_parser("search")
    searching.add_argument("question")
    searching.add_argument("--assigned-center", required=True, help="Development identity simulation")
    searching.add_argument("--week-start", help="Defaults to the latest completed week at run time")
    args = parser.parse_args()
    try:
        if args.command == "prepare":
            print(json.dumps(prepare_documents(args.data_dir or active_data_dir())[0], indent=2))
        elif args.command == "index":
            index_documents(args.data_dir, args.create_index)
        else:
            result = CenterDocumentSearch(args.data_dir, args.assigned_center).search(args.question, args.week_start)
            print(json.dumps(result, indent=2))
    except (ValueError, FileNotFoundError) as exc:
        parser.exit(2, f"Retrieval setup: {exc}\n")
