"""Exercise the local Streamlit interface without making paid API requests."""

import sys
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


class AppTests(unittest.TestCase):
    def setUp(self):
        clock = patch("center_copilot.reporting.runtime_date", return_value=date(2026, 10, 20))
        clock.start()
        self.addCleanup(clock.stop)

    def app(self):
        return AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run()

    def test_initial_dashboard_and_scope_selection(self):
        app = self.app()
        self.assertFalse(app.exception)
        self.assertEqual(app.metric[0].value, "$28,900")
        self.assertEqual(app.selectbox(key="week").value, "2026-10-11")
        app.selectbox(key="center").select("C002").run()
        self.assertFalse(app.exception)
        self.assertEqual(app.metric[0].value, "$36,057")

    def test_question_is_scoped_and_answer_clears_on_change(self):
        fake = {"answer": "Revenue was below target. [S1]", "sources": [
            {"citation": "[S1]", "kind": "sql", "center_id": "C001", "week_start": "2026-10-11"}],
            "tools_used": ["get_center_metrics"]}
        app = self.app()
        with patch("center_copilot.agent.answer_question", return_value=fake) as answer:
            app.text_area(key="question").set_value("How did we perform?")
            app.button[0].click().run()
            self.assertFalse(app.exception)
            self.assertEqual(answer.call_args.args[1:3], ("C001", "2026-10-11"))
            self.assertTrue(app.chat_message)
            app.run()
            answer.assert_called_once()
            app.selectbox(key="week").select("2026-10-04").run()
            self.assertFalse(app.chat_message)
            answer.assert_called_once()

    def test_empty_question_does_not_call_agent(self):
        app = self.app()
        with patch("center_copilot.agent.answer_question") as answer:
            app.text_area(key="question").set_value("   ")
            app.button[0].click().run()
            answer.assert_not_called()
        self.assertIn("Enter a question", app.error[0].value)

    def test_service_errors_do_not_expose_private_details(self):
        app = self.app()
        with patch("center_copilot.agent.answer_question", side_effect=RuntimeError("private-api-key")):
            app.button[0].click().run()
        self.assertFalse(app.exception)
        self.assertIn("RuntimeError", app.error[0].value)
        self.assertNotIn("private-api-key", app.error[0].value)

    def test_answer_validation_failure_has_actionable_message(self):
        from center_copilot.agent import AnswerValidationError
        app = self.app()
        with patch("center_copilot.agent.answer_question", side_effect=AnswerValidationError("unknown_sources")):
            app.button[0].click().run()
        self.assertFalse(app.exception)
        self.assertIn("could not be verified", app.error[0].value)
        self.assertNotIn("credentials", app.error[0].value)


if __name__ == "__main__":
    unittest.main()
