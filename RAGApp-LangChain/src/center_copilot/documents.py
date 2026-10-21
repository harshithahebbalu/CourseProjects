"""Prepare only manifest-listed Markdown documents, without API calls."""

import hashlib
import html
import json
import os
import re
import sqlite3
from contextlib import closing
from datetime import date
from pathlib import Path

import tiktoken

MODEL = "text-embedding-3-small"
DIMENSIONS = 1536
CHUNK_SIZE = 500
OVERLAP = 75


def tokenizer():
    # Keep tokenizer assets within the writable workspace, not the user's temp folder.
    cache = Path(__file__).resolve().parents[2] / "data" / "tokenizer_cache"
    cache.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("TIKTOKEN_CACHE_DIR", str(cache))
    return tiktoken.encoding_for_model(MODEL)


def digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def clean_text(text):
    text = html.unescape(text).replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def split_document(text, title, encoding):
    """Preserve section boundaries; use overlapping token windows only for long sections.

    Small sections deliberately stay below 500 tokens rather than mixing unrelated
    headings. A token boundary may split a UTF-8 character, so expand to valid boundaries.
    """
    sections = re.split(r"(?m)^## ", clean_text(text))
    # The generated preamble is administrative metadata already preserved per chunk.
    if len(sections) == 1:
        sections = ["Content\n" + sections[0]]
    else:
        sections = sections[1:]
    for section in sections:
        heading, _, body = section.partition("\n")
        if not body.strip():
            continue
        prefix = f"# {title}\n\n## {heading.strip()}\n\n"
        budget = CHUNK_SIZE - len(encoding.encode(prefix, disallowed_special=()))
        if budget <= OVERLAP:
            raise ValueError("Document heading is too long for the chunk budget")
        tokens = encoding.encode(body.strip(), disallowed_special=())
        start = 0
        while start < len(tokens):
            end = min(start + budget, len(tokens))
            # Move the end backward until this window decodes without replacement characters.
            while end > start:
                try:
                    body_part = encoding.decode(tokens[start:end], errors="strict")
                    break
                except UnicodeDecodeError:
                    end -= 1
            if end == start:
                raise ValueError("Could not find a UTF-8 token boundary")
            yield heading.strip(), prefix + body_part
            if end == len(tokens):
                break
            next_start = max(start + 1, end - OVERLAP)
            while next_start < end:
                try:
                    encoding.decode(tokens[next_start:end], errors="strict")
                    break
                except UnicodeDecodeError:
                    next_start += 1
            start = next_start


def prepare_documents(data_dir):
    data_dir = Path(data_dir).resolve()
    encoding = tokenizer()
    with closing(sqlite3.connect((data_dir / "center_performance.sqlite").as_uri() + "?mode=ro", uri=True)) as conn:
        conn.row_factory = sqlite3.Row
        manifest = [dict(r) for r in conn.execute("SELECT * FROM document_manifest ORDER BY document_id")]
    if not manifest:
        raise ValueError("Document manifest is empty")
    chunks = []
    for doc in manifest:
        source = (data_dir / doc["source_path"]).resolve()
        if not source.is_relative_to(data_dir / "documents") or source.suffix != ".md":
            raise ValueError("Only Markdown files inside data/documents are supported in this MVP")
        text = source.read_text(encoding="utf-8")
        pieces = list(split_document(text, doc["title"], encoding))
        if not pieces:
            raise ValueError(f"Document has no readable content: {doc['document_id']}")
        for number, (section, content) in enumerate(pieces):
            count = len(encoding.encode(content, disallowed_special=()))
            if count > CHUNK_SIZE:
                raise ValueError("Chunk exceeded token budget")
            fields = {
                "document_id": doc["document_id"], "title": doc["title"],
                "document_type": doc["document_type"], "scope": doc["center_id"] or "shared",
                "week_start": doc["week_start"] or "shared", "version": doc["version"],
                "effective_from": date.fromisoformat(doc["effective_from"]).toordinal(),
                "effective_to": date.fromisoformat(doc["effective_to"]).toordinal() if doc["effective_to"] else date.max.toordinal(),
                "source_path": doc["source_path"], "section": section,
                "text": content, "token_count": count, "source_hash": digest(text),
            }
            chunks.append({"id": f"{doc['document_id']}:v{doc['version']}:{number}", "fields": fields})
    canonical = json.dumps({"model": MODEL, "dimensions": DIMENSIONS, "chunk_size": CHUNK_SIZE,
                            "overlap": OVERLAP, "chunks": chunks}, sort_keys=True, ensure_ascii=False)
    snapshot = digest(canonical)
    plan = {"model": MODEL, "dimensions": DIMENSIONS, "chunk_size": CHUNK_SIZE, "overlap": OVERLAP,
            "documents": len(manifest), "chunks": len(chunks),
            "embedding_input_tokens": sum(c["fields"]["token_count"] for c in chunks),
            "snapshot": snapshot, "namespace": f"synthetic-{snapshot[:16]}"}
    folder = data_dir / "retrieval"
    folder.mkdir(exist_ok=True)
    (folder / "chunks.jsonl").write_text("".join(json.dumps(c, ensure_ascii=False) + "\n" for c in chunks), encoding="utf-8")
    (folder / "plan.json").write_text(json.dumps(plan, indent=2), encoding="utf-8")
    return plan, chunks
