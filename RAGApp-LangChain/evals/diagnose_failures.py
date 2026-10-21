"""Reproduce baseline failures while preserving rejected answers, without changing prompts."""

import json
import sys
import traceback
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import center_copilot.agent as agent


def main():
    benchmark = json.loads((ROOT / "evals/benchmark.json").read_text())
    original = agent.validate_citations
    output = ROOT / "data/evals/failure_diagnosis.json"
    findings = []
    for case in benchmark["cases"]:
        if case["id"] not in ("sql_08", "boundary_03"):
            continue
        finding = {"id": case["id"], "question": case["question"]}

        def inspect(answer, ledger):
            finding["candidate_answer"] = answer
            finding["available_labels"] = list(ledger.sources)
            try:
                return original(answer, ledger)
            except ValueError as exc:
                finding["validation_reason"] = str(exc)
                raise

        try:
            with patch.object(agent, "validate_citations", side_effect=inspect):
                finding["result"] = agent.answer_question(case["question"], case["center"], case["week_start"])
        except Exception as exc:
            finding["error"] = type(exc).__name__
            # Frames only: no provider response bodies, local values, or keys.
            finding["frames"] = [{"file": Path(f.filename).name, "line": f.lineno, "function": f.name}
                                 for f in traceback.extract_tb(exc.__traceback__)]
        findings.append(finding)
        output.write_text(json.dumps(findings, indent=2), encoding="utf-8")
        print(json.dumps(finding), flush=True)


if __name__ == "__main__":
    main()
