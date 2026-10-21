"""Date rollover tests use injected dates, without changing the real system clock."""

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import date
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from center_copilot.analytics import CenterAnalytics
from center_copilot.reporting import dataset_window, latest_completed_week, synthetic_holidays
from center_copilot.runtime_data import active_data_dir, ensure_snapshot_index


class ReportingTests(unittest.TestCase):
    def test_saturday_remains_partial_and_sunday_rolls_forward(self):
        self.assertEqual(latest_completed_week(date(2026, 10, 24)), date(2026, 10, 11))
        self.assertEqual(latest_completed_week(date(2026, 10, 25)), date(2026, 10, 18))

    def test_year_boundary_and_52_complete_weeks(self):
        start, end = dataset_window(date(2027, 1, 3))
        self.assertEqual(end, date(2027, 1, 2))
        self.assertEqual(start.weekday(), 6)
        self.assertEqual((end - start).days + 1, 364)

    def test_clock_is_resolved_on_each_analytics_call(self):
        tool = CenterAnalytics(ROOT / "data/center_performance.sqlite", "C001")
        with patch("center_copilot.analytics.runtime_date", return_value=date(2026, 10, 20)):
            self.assertEqual(tool.weekly_performance()["reference_date"], "2026-10-20")
        with patch("center_copilot.analytics.runtime_date", return_value=date(2026, 10, 21)):
            self.assertEqual(tool.weekly_performance()["reference_date"], "2026-10-21")

    def test_new_snapshot_is_reused_and_old_week_preserved(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "data") as temporary, redirect_stdout(io.StringIO()):
            base = Path(temporary)
            first = active_data_dir(date(2026, 10, 20), base)
            self.assertEqual(first, active_data_dir(date(2026, 10, 24), base))
            second = active_data_dir(date(2026, 10, 25), base)
            self.assertNotEqual(first, second)
            self.assertTrue((first / "center_performance.sqlite").exists())
            summary = json.loads((second / "generation_summary.json").read_text())
            self.assertEqual(summary["end"], "2026-10-24")
            self.assertEqual(summary["latest_week"][0]["week_start"], "2026-10-18")

    def test_holiday_calendar_extends_to_future_years(self):
        holidays = synthetic_holidays(date(2027, 1, 1), date(2027, 12, 31))
        self.assertIn(date(2027, 11, 25), holidays)
        self.assertIn(date(2027, 5, 31), holidays)

    def test_new_snapshot_indexes_once_when_requested(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "data") as temporary:
            folder = Path(temporary)
            (folder / "runtime_snapshot.json").write_text("{}")

            def complete_index(path, create=False):
                (path / "retrieval").mkdir()
                (path / "retrieval/index_state.json").write_text("{}")

            with patch("center_copilot.retrieval.index_documents", side_effect=complete_index) as indexing:
                ensure_snapshot_index(folder)
                ensure_snapshot_index(folder)
                indexing.assert_called_once_with(folder, create=True)

    def test_historical_snapshot_is_not_automatically_indexed(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "data") as temporary:
            with patch("center_copilot.retrieval.index_documents") as indexing:
                ensure_snapshot_index(Path(temporary))
                indexing.assert_not_called()


if __name__ == "__main__":
    unittest.main()
