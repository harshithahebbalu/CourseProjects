"""Reuse a current weekly dataset or build a new local snapshot without deleting history."""

import json
from pathlib import Path
from threading import Lock
from uuid import uuid4

try:
    from .reporting import runtime_date, dataset_window
except ImportError:
    from reporting import runtime_date, dataset_window

ROOT = Path(__file__).resolve().parents[2]
_generation_lock = Lock()
_index_lock = Lock()


def active_data_dir(reference=None, base=None):
    reference = reference or runtime_date()
    base = Path(base or ROOT / "data").resolve()
    start, end = dataset_window(reference)
    with _generation_lock:
        for candidate in (base, base / "snapshots" / str(end)):
            manifest = candidate / "generation_summary.json"
            if manifest.exists():
                summary = json.loads(manifest.read_text(encoding="utf-8"))
                if summary["start"] == str(start) and summary["end"] == str(end):
                    return candidate
        try:
            from .generate_data import generate
        except ImportError:
            from generate_data import generate
        target = base / "snapshots" / str(end)
        staging = target.parent / f".building-{uuid4().hex}"
        generate(staging, reference_date=reference)
        # Mark only auto-generated snapshots for lazy first-question indexing.
        (staging / "runtime_snapshot.json").write_text(json.dumps({"generated_for": str(reference)}), encoding="utf-8")
        staging.rename(target)
        return target


def ensure_snapshot_index(data_dir):
    """Index a new rolling snapshot once, when a paid question is submitted."""
    data_dir = Path(data_dir)
    if not (data_dir / "runtime_snapshot.json").exists():
        return
    with _index_lock:
        if not (data_dir / "retrieval/index_state.json").exists():
            try:
                from .retrieval import index_documents
            except ImportError:
                from retrieval import index_documents
            index_documents(data_dir, create=True)
