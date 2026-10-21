"""Run local numeric checks, live retrieval checks, and bounded live agent checks."""

import argparse
import csv
import hashlib
import json
import math
import os
import re
import sys
import time
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from center_copilot.analytics import CenterAnalytics


def scope_ok(sources, case):
    for source in sources:
        if source["kind"] == "sql":
            if source["center_id"] != case["center"] or source["week_start"] != case["week_start"]:
                return False
        elif source.get("scope") != "shared":
            if source.get("scope") != case["center"] or source.get("week_start") != case["week_start"]:
                return False
    return True


def value_presence(answer, values):
    """A weak screen: magnitudes occurring in prose, not claim-level correctness."""
    cleaned = re.sub(r"\[S\d+\]", "", answer)
    numbers = [abs(float(n.replace(",", ""))) for n in re.findall(r"[-+]?\d[\d,]*(?:\.\d+)?", cleaned)]
    return {name: any(math.isclose(abs(expected), found, abs_tol=.51 if "revenue" in name else .11) for found in numbers)
            for name, expected in values.items()}


def numeric_checks(case):
    result = CenterAnalytics(ROOT / "data/center_performance.sqlite", case["center"]).weekly_performance(case["week_start"])
    actual = result["actuals"]
    values = {**actual, **result["targets"], "revenue_variance": result["versus_target"]["revenue"]["difference"],
              "staffed_occupancy_percent": actual["staffed_occupancy"] * 100}
    return {key: math.isclose(values[key], expected, abs_tol=1e-7) for key, expected in case["expected_values"].items()}


def retrieval_checks(case, search):
    result = search.search(case["question"], case["week_start"], top_k=6)
    ids = {m["chunk_id"] for m in result["matches"]}
    relevant = set(case["relevant_chunks"])
    matches = [{"kind": "document", **m} for m in result["matches"]]
    return {"checks": {"scope": scope_ok(matches, case)}, "recall_at_6": len(ids & relevant) / len(relevant),
            "relevant_hits": len(ids & relevant), "relevant_total": len(relevant),
            "returned_chunks": sorted(ids), "missing_chunks": sorted(relevant - ids)}


def agent_checks(case, result):
    sources = result.get("available_sources", result["sources"])
    checks = {"scope": scope_ok(sources, case),
              "required_tools": set(case["required_tools"]) <= set(result["tools_used"])}
    present = value_presence(result["answer"], case["expected_values"])
    checks.update({"value_present:" + name: passed for name, passed in present.items()})
    return {"checks": checks, "result": result, "human_review": "pending"}


def save_reports(output, rows, metadata):
    stages = {}
    for stage in ("offline", "retrieval", "agent"):
        subset = [r for r in rows if r["stage"] == stage]
        if not subset:
            continue
        stages[stage] = {"cases": len(subset), "errors": sum("error" in r for r in subset),
                         "automatic_checks_passed": sum("error" not in r and all(r.get("checks", {}).values()) for r in subset)}
        if stage == "retrieval":
            total = sum(r.get("relevant_total", 0) for r in subset)
            hits = sum(r.get("relevant_hits", 0) for r in subset)
            stages[stage].update({"relevant_hits": hits, "relevant_total": total,
                                  "micro_recall_at_6": hits / total if total else None,
                                  "macro_recall_at_6": sum(r.get("recall_at_6", 0) for r in subset) / len(subset)})
    report = {**metadata, "stages": stages, "human_review_status": "pending",
              "limitations": ["Automatic agent checks measure routing, source scope, and expected-number presence, not factual or causal correctness.",
                              "Citation support, semantic abstention, applicability of policy versions, and action quality require human review.",
                              "Fixed development suite; one run is not evidence of production reliability."]}
    (output / "summary.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    # Do not overwrite a reviewer-edited sheet on resume: generate a separate template.
    with (output / "human_review_template.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        fields = ["id", "question", "answer", "rubric", "numerical_correctness", "citation_support", "causal_caution", "scope_and_abstention", "action_quality", "reviewer_notes"]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            if row["stage"] == "agent":
                writer.writerow({"id": row["id"], "question": row["question"], "answer": row.get("result", {}).get("answer", row.get("error", "")),
                                 "rubric": row["rubric"]})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["offline", "retrieval", "agent", "all"], default="offline")
    parser.add_argument("--output", type=Path, default=ROOT / "data/evals/baseline")
    parser.add_argument("--limit", type=int, help="Limit agent cases only; omitted means all 30")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be positive")
    benchmark_bytes = (ROOT / "evals/benchmark.json").read_bytes()
    benchmark = json.loads(benchmark_bytes)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    log = output / "results.jsonl"
    if log.exists() and not args.resume:
        parser.error("Output already has results; use --resume or a new --output directory")
    signature = hashlib.sha256(benchmark_bytes + b"".join((ROOT / p).read_bytes() for p in
        ("src/center_copilot/agent.py", "src/center_copilot/analytics.py", "src/center_copilot/retrieval.py",
         "evals/run.py", "evals/build_benchmark.py", "data/center_performance.sqlite", "data/retrieval/index_state.json"))).hexdigest()
    if args.mode != "offline":
        from center_copilot.retrieval import settings
        settings()
    metadata = {"started_at_utc": datetime.now(timezone.utc).isoformat(), "benchmark_cases": len(benchmark["cases"]),
                "category_counts": dict(Counter(c["category"] for c in benchmark["cases"])),
                "signature": signature, "chat_model": os.getenv("OPENAI_CHAT_MODEL", "gpt-4.1-mini"),
                "embedding_model": "text-embedding-3-small", "mode": args.mode}
    if args.resume and (output / "summary.json").exists():
        prior = json.loads((output / "summary.json").read_text(encoding="utf-8"))
        if prior["signature"] != signature or prior["chat_model"] != metadata["chat_model"]:
            parser.error("Code, benchmark, dataset, index, or model changed; use a new output directory")
    rows = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()] if log.exists() else []
    done = {(r["stage"], r["id"]) for r in rows}
    tasks = []
    if args.mode in ("offline", "all"):
        tasks += [("offline", c) for c in benchmark["cases"] if c["category"] == "sql"]
    if args.mode in ("retrieval", "all"):
        tasks += [("retrieval", c) for c in benchmark["cases"] if c["relevant_chunks"]]
    if args.mode in ("agent", "all"):
        tasks += [("agent", c) for c in benchmark["cases"][:args.limit]]
    for stage, case in tasks:
        if (stage, case["id"]) in done:
            continue
        started = time.perf_counter()
        row = {"stage": stage, "id": case["id"], "category": case["category"], "question": case["question"], "rubric": case["review_rubric"]}
        try:
            if stage == "offline":
                row["checks"] = numeric_checks(case)
            elif stage == "retrieval":
                from center_copilot.retrieval import CenterDocumentSearch
                row.update(retrieval_checks(case, CenterDocumentSearch(ROOT / "data", case["center"])))
            else:
                from center_copilot.agent import answer_question
                row.update(agent_checks(case, answer_question(case["question"], case["center"], case["week_start"])))
        except Exception as exc:
            row["error"] = type(exc).__name__
            if getattr(exc, "code", None):
                row["error_code"] = exc.code
        row["seconds"] = round(time.perf_counter() - started, 2)
        with log.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row) + "\n")
        rows.append(row)
        save_reports(output, rows, metadata)
        print(f"{stage} {case['id']}: {row.get('error', 'checks passed' if all(row.get('checks', {}).values()) else 'review flagged')} ({row['seconds']}s)", flush=True)
    save_reports(output, rows, metadata)
    print(json.dumps(json.loads((output / "summary.json").read_text()), indent=2))


if __name__ == "__main__":
    main()
