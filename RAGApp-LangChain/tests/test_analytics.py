"""Behavioral checks against the generated synthetic dataset; no API calls."""

import sqlite3
import sys
import unittest
from datetime import date
from contextlib import closing
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from center_copilot.analytics import CenterAnalytics, change


class AnalyticsTests(unittest.TestCase):
    def setUp(self):
        self.tool = CenterAnalytics(ROOT / "data/center_performance.sqlite", "C001", reference_date=date(2026, 10, 19))

    def test_known_latest_week(self):
        result = self.tool.weekly_performance()
        self.assertEqual(result["week_start"], "2026-10-11")
        self.assertEqual(result["week_end"], "2026-10-17")
        self.assertEqual(result["actuals"]["actual_revenue"], 28900)
        self.assertEqual(result["versus_target"]["revenue"]["difference"], -5950)
        self.assertAlmostEqual(result["actuals"]["staffed_occupancy"], 68 / 70)

    def test_independent_prior_four_week_calculation(self):
        result = self.tool.weekly_performance()
        with closing(sqlite3.connect(self.tool.database)) as conn:
            revenues = [r[0] for r in conn.execute(
                "SELECT earned_tuition_revenue FROM daily_performance "
                "WHERE center_id='C001' AND service_date BETWEEN '2026-09-13' AND '2026-10-10'")]
        self.assertAlmostEqual(result["prior_four_weeks"]["averages"]["actual_revenue"], sum(revenues) / 4)
        self.assertEqual(result["prior_four_weeks"]["complete_weeks"], 4)

    def test_short_history_is_explicit(self):
        result = self.tool.weekly_performance("2025-10-26")
        self.assertTrue(result["previous_week"]["available"])
        self.assertFalse(result["prior_four_weeks"]["available"])
        self.assertIsNone(result["prior_four_weeks"]["averages"]["actual_revenue"])

    def test_reject_partial_invalid_and_missing_weeks(self):
        for week in ("2026-10-18", "2026-10-12", "2025-10-12", "not-a-date"):
            with self.subTest(week=week), self.assertRaises(ValueError):
                self.tool.weekly_performance(week)

    def test_no_caller_controlled_center_argument(self):
        with self.assertRaises(TypeError):
            self.tool.weekly_performance(center_id="C002")
        self.assertEqual(self.tool.weekly_performance()["actuals"]["center_id"], "C001")

    def test_connection_refuses_mutation(self):
        with closing(self.tool._connect()) as conn:
            with self.assertRaises(sqlite3.OperationalError):
                conn.execute("DELETE FROM daily_performance WHERE center_id='C001'")

    def test_zero_missing_and_negative_baselines(self):
        self.assertIsNone(change(10, 0)["percent_change"])
        self.assertIsNone(change(None, 10)["difference"])
        self.assertEqual(change(80, 100)["percent_change"], -20)


if __name__ == "__main__":
    unittest.main()
