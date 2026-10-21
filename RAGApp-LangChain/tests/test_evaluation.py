"""Check that the evaluator can flag wrong scope and missing expected values."""

import json
import runpy
import unittest
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
EVAL = runpy.run_path(str(ROOT / "evals/run.py"))


class EvaluationTests(unittest.TestCase):
    def test_benchmark_has_promised_coverage_and_independent_numeric_answers(self):
        cases = json.loads((ROOT / "evals/benchmark.json").read_text())["cases"]
        self.assertEqual(Counter(c["category"] for c in cases), {"sql": 10, "document": 8, "combined": 8, "boundary": 4})
        for case in cases[:10]:
            self.assertTrue(all(EVAL["numeric_checks"](case).values()))

    def test_wrong_center_or_reporting_week_is_rejected(self):
        case = {"center": "C001", "week_start": "2026-10-11"}
        self.assertFalse(EVAL["scope_ok"]([{"kind": "sql", "center_id": "C002", "week_start": "2026-10-11"}], case))
        self.assertFalse(EVAL["scope_ok"]([{"kind": "document", "scope": "C001", "week_start": "2026-10-04"}], case))
        self.assertTrue(EVAL["scope_ok"]([{"kind": "document", "scope": "shared"}], case))

    def test_number_screen_does_not_accept_missing_expected_value(self):
        checks = EVAL["value_presence"]("Revenue was $28,900. [S1]", {"revenue": 28900, "variance": -5950})
        self.assertTrue(checks["revenue"])
        self.assertFalse(checks["variance"])

    def test_recall_counts_missing_relevant_chunks(self):
        case = {"question": "test", "center": "C001", "week_start": "2026-10-11", "relevant_chunks": ["a", "b"]}
        search = SimpleNamespace(search=lambda *args, **kwargs: {"matches": [
            {"chunk_id": "a", "scope": "C001", "week_start": "2026-10-11"}]})
        result = EVAL["retrieval_checks"](case, search)
        self.assertEqual(result["recall_at_6"], .5)
        self.assertEqual(result["missing_chunks"], ["b"])


if __name__ == "__main__":
    unittest.main()
