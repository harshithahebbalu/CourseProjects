"""Local retrieval boundary checks; API behavior and relevance need live evaluation."""

import json
import sqlite3
import sys
import unittest
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from unittest.mock import patch
from datetime import date

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from center_copilot.documents import CHUNK_SIZE, clean_text, prepare_documents, split_document, tokenizer
from center_copilot.retrieval import CenterDocumentSearch, embed_cached, evidence_filter, select_evidence


def matches_filter(fields, expression):
    """Independent minimal evaluator for the subset of Pinecone filters used here."""
    for key, value in expression.items():
        if key == "$and" and not all(matches_filter(fields, e) for e in value):
            return False
        if key == "$or" and not any(matches_filter(fields, e) for e in value):
            return False
        if key.startswith("$"):
            continue
        for operator, expected in value.items():
            actual = fields.get(key)
            if actual is None:
                return False
            if operator == "$eq" and actual != expected:
                return False
            if operator == "$lte" and actual > expected:
                return False
            if operator == "$gte" and actual < expected:
                return False
    return True


class RetrievalTests(unittest.TestCase):
    def setUp(self):
        clock = patch("center_copilot.retrieval.runtime_date", return_value=date(2026, 10, 20))
        clock.start()
        self.addCleanup(clock.stop)

    @classmethod
    def setUpClass(cls):
        cls.plan, cls.chunks = prepare_documents(ROOT / "data")

    def test_only_manifest_documents_and_token_limits(self):
        self.assertEqual(self.plan["documents"], 524)
        self.assertEqual(len({c["id"] for c in self.chunks}), len(self.chunks))
        self.assertTrue(all(0 < c["fields"]["token_count"] <= CHUNK_SIZE for c in self.chunks))
        self.assertTrue(all(c["fields"]["source_path"].startswith("documents/") for c in self.chunks))
        self.assertFalse(any("scenario_labels" in c["fields"]["text"] for c in self.chunks))

    def test_center_week_and_guidance_boundaries(self):
        filters = evidence_filter("C001", "2026-10-11")
        eligible = [c["fields"] for c in self.chunks if matches_filter(c["fields"], filters)]
        self.assertTrue(any("teacher vacancy" in c["text"] for c in eligible))
        self.assertEqual({c["scope"] for c in eligible}, {"C001", "shared"})
        self.assertEqual({c["week_start"] for c in eligible if c["scope"] != "shared"}, {"2026-10-11"})
        self.assertEqual(len({c["document_id"] for c in eligible}), 5)
        guidance = next(c for c in eligible if c["scope"] == "shared")
        self.assertFalse(matches_filter({**guidance, "effective_from": 9999999}, filters))
        self.assertFalse(matches_filter({**guidance, "effective_to": 1}, filters))

    def test_invalid_dates_and_identity(self):
        for week in ("2026-10-12", "2026-10-18"):
            with self.assertRaises(ValueError):
                evidence_filter("C001", week)
        with self.assertRaises(ValueError):
            CenterDocumentSearch(ROOT / "data", "C999")
        search = CenterDocumentSearch(ROOT / "data", "C001")
        with self.assertRaises(TypeError):
            search.search("question", assigned_center="C002")

    def test_cleanup_and_long_unicode_sections(self):
        self.assertEqual(clean_text("A &amp; B\r\n\r\n\r\nC"), "A & B\n\nC")
        parts = list(split_document("## Notes\n" + "Childcare café 教育 🙂 " * 1000, "Sample", tokenizer()))
        self.assertGreater(len(parts), 1)
        for heading, text in parts:
            self.assertEqual(heading, "Notes")
            self.assertNotIn("\ufffd", text)
            self.assertLessEqual(len(tokenizer().encode(text)), CHUNK_SIZE)

    def test_embedding_cache_avoids_repeat_api_calls(self):
        client = SimpleNamespace(embeddings=Mock())
        client.embeddings.create.return_value = SimpleNamespace(data=[
            SimpleNamespace(index=1, embedding=[.2] * 1536),
            SimpleNamespace(index=0, embedding=[.1] * 1536)])
        with closing(sqlite3.connect(":memory:")) as cache:
            first = embed_cached(client, cache, ["one", "two"])
            second = embed_cached(client, cache, ["two", "one"])
        self.assertEqual(first[0], second[1])
        self.assertEqual(first[1], second[0])
        client.embeddings.create.assert_called_once()

    def test_snapshot_is_reproducible(self):
        second, _ = prepare_documents(ROOT / "data")
        self.assertEqual(self.plan["snapshot"], second["snapshot"])

    def test_guidance_is_not_crowded_out_by_report_sections(self):
        reports = [{"chunk_id": f"r{i}", "section": "Performance"} for i in range(4)]
        reports[-1]["section"] = "Director observations"
        guides = [{"chunk_id": f"g{i}", "section": "Content"} for i in range(4)]
        result = select_evidence(reports, guides, 6)
        self.assertEqual(len(result), 6)
        self.assertIn("r3", {m["chunk_id"] for m in result})
        self.assertEqual(sum(m["chunk_id"].startswith("g") for m in result), 3)

    def test_unused_evidence_slots_are_filled_without_duplicates(self):
        reports = [{"chunk_id": "r", "section": "Director observations"}]
        guides = [{"chunk_id": f"g{i}"} for i in range(5)]
        result = select_evidence(reports, guides, 6)
        self.assertEqual(len(result), 6)
        self.assertEqual(len({m["chunk_id"] for m in result}), 6)


if __name__ == "__main__":
    unittest.main()
