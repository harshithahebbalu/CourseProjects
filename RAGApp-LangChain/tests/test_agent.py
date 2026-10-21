"""Test the actual LangChain tool loop locally without a live language model."""

import sys
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from center_copilot.agent import AnswerValidationError, EvidenceLedger, answer_question, build_tools, normalize_citations, validate_citations


class ScriptedModel(FakeMessagesListChatModel):
    def bind_tools(self, tools, **kwargs):
        return self


class AgentTests(unittest.TestCase):
    def setUp(self):
        clock = patch("center_copilot.agent.runtime_date", return_value=date(2026, 10, 20))
        clock.start()
        self.addCleanup(clock.stop)

    def test_tool_schemas_cannot_override_center_or_week(self):
        tools, _ = build_tools(ROOT / "data", "C001", "2026-10-11")
        self.assertEqual(tools[0].args, {})
        self.assertEqual(set(tools[1].args), {"question"})

    def test_actual_langchain_sql_loop(self):
        model = ScriptedModel(responses=[
            AIMessage(content="", tool_calls=[{"name": "get_center_metrics", "args": {}, "id": "call_sql"}]),
            AIMessage(content="Revenue was $28,900, which was $5,950 below target. [S1]")])
        result = answer_question("How did my center perform?", "C001", model=model)
        self.assertEqual(result["tools_used"], ["get_center_metrics"])
        self.assertEqual(result["sources"][0]["kind"], "sql")
        self.assertEqual(result["sources"][0]["center_id"], "C001")

    def test_document_sources_use_actual_returned_passage(self):
        passage = {"chunk_id": "capacity:v1:0", "document_id": "capacity", "source_path": "documents/capacity.md",
                   "title": "Capacity", "section": "Content", "version": 1, "scope": "shared", "week_start": "shared",
                   "text": "Check staffed capacity before offering seats."}
        with patch("center_copilot.agent.CenterDocumentSearch.search", return_value={"matches": [passage]}):
            tools, ledger = build_tools(ROOT / "data", "C001", "2026-10-11")
            result = tools[1].invoke({"question": "How do I review capacity?"})
        self.assertEqual(result["matches"][0]["citation"], "[S1]")
        self.assertEqual(ledger.sources["S1"]["source_path"], "documents/capacity.md")

    def test_retrieval_failure_is_explicit_and_does_not_leak_errors(self):
        with patch("center_copilot.agent.CenterDocumentSearch.search", side_effect=RuntimeError("private details")):
            tools, ledger = build_tools(ROOT / "data", "C001", "2026-10-11")
            result = tools[1].invoke({"question": "Why?"})
        self.assertIn("RuntimeError", result["error"])
        self.assertNotIn("private details", str(result))
        self.assertFalse(ledger.sources)

    def test_unknown_or_missing_citations_are_rejected(self):
        ledger = EvidenceLedger()
        ledger.add("sql", {"kind": "sql"})
        for answer in ("A claim [S99]", "A claim without citations"):
            with self.assertRaises(ValueError):
                validate_citations(answer, ledger)

    def test_grouped_citations_keep_all_sources_and_reject_unknown_ids(self):
        ledger = EvidenceLedger()
        ledger.add("one", {"kind": "sql"})
        ledger.add("two", {"kind": "document"})
        answer = normalize_citations("Supported [S1, S2]; also [S2; S1].")
        self.assertEqual(answer, "Supported [S1][S2]; also [S2][S1].")
        self.assertEqual(len(validate_citations(answer, ledger)), 2)
        with self.assertRaises(AnswerValidationError) as failure:
            validate_citations("Claim [S1, S99]", ledger)
        self.assertEqual(failure.exception.code, "unknown_sources")

    def test_missing_citation_gets_one_evidence_preserving_repair(self):
        model = ScriptedModel(responses=[
            AIMessage(content="", tool_calls=[{"name": "get_center_metrics", "args": {}, "id": "sql"}]),
            AIMessage(content="Revenue was $28,900."),
            AIMessage(content="Revenue was $28,900. [S1]")])
        result = answer_question("What was revenue?", "C001", model=model)
        self.assertEqual(result["validation_repairs"], 1)
        self.assertEqual(result["sources"][0]["citation"], "[S1]")
        self.assertEqual(result["tools_used"], ["get_center_metrics"])

    def test_second_invalid_answer_is_rejected(self):
        model = ScriptedModel(responses=[
            AIMessage(content="", tool_calls=[{"name": "get_center_metrics", "args": {}, "id": "sql"}]),
            AIMessage(content="Revenue was $28,900."),
            AIMessage(content="Revenue was $28,900. [S99]")])
        with self.assertRaises(AnswerValidationError) as failure:
            answer_question("What was revenue?", "C001", model=model)
        self.assertEqual(failure.exception.code, "unknown_sources")

    def test_revenue_cannot_be_relabeled_as_ebitda(self):
        model = ScriptedModel(responses=[
            AIMessage(content="", tool_calls=[{"name": "get_center_metrics", "args": {}, "id": "sql"}]),
            AIMessage(content="EBITDA was $28,900. [S1]"),
            AIMessage(content="EBITDA cannot be calculated because expense data are unavailable. [S1]")])
        result = answer_question("What was EBITDA?", "C001", model=model)
        self.assertEqual(result["validation_repairs"], 1)
        self.assertNotIn("$28,900", result["answer"])


if __name__ == "__main__":
    unittest.main()
