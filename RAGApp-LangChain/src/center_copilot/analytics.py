"""Read-only, center-scoped analytics. No model-generated SQL is executed."""

import argparse
import json
import sqlite3
from contextlib import closing
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
try:
    from .reporting import runtime_date
except ImportError:
    from reporting import runtime_date
METRICS = ("actual_revenue", "avg_enrolled_fte", "avg_staffed_capacity",
           "staffed_occupancy", "inquiries", "tours", "new_enrollments", "withdrawals")


def change(actual, baseline):
    """Return signed absolute and percentage change; undefined values stay null."""
    delta = None if actual is None or baseline is None else actual - baseline
    return {"baseline": baseline, "difference": delta,
            "percent_change": None if delta is None or baseline == 0 else delta / baseline * 100}


class CenterAnalytics:
    """Bind assigned_center from trusted application identity, never agent input.

    The CLI assignment is a development simulation, not authentication. An eventual
    agent tool exposes only week_start and closes over this instance.
    """

    def __init__(self, database, assigned_center, reference_date=None):
        self.database = Path(database).resolve()
        self.assigned_center = assigned_center
        self.reference_date = reference_date

    def _connect(self):
        conn = sqlite3.connect(self.database.as_uri() + "?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA query_only=ON")
        return conn

    def weekly_performance(self, week_start=None):
        """Get one completed Sunday-Saturday week with explicit missing-data status."""
        reference = self.reference_date or runtime_date()
        current_sunday = reference - timedelta(days=(reference.weekday() + 1) % 7)
        start = date.fromisoformat(week_start) if week_start else current_sunday - timedelta(days=7)
        if start.weekday() != 6:
            raise ValueError("week_start must be a Sunday in YYYY-MM-DD format")
        end = start + timedelta(days=6)
        if end >= reference:
            raise ValueError("Only completed weeks before the reference date are supported")
        with closing(self._connect()) as conn:
            center = conn.execute("SELECT * FROM centers WHERE center_id=?",
                                  (self.assigned_center,)).fetchone()
            if center is None:
                raise ValueError("Assigned center does not exist")
            rows = conn.execute(
                "SELECT * FROM weekly_actuals WHERE center_id=? AND week_start BETWEEN ? AND ? ORDER BY week_start",
                (self.assigned_center, str(start - timedelta(weeks=4)), str(start))).fetchall()
            by_week = {r["week_start"]: dict(r) for r in rows}
            selected = by_week.get(str(start))
            if selected is None or selected["recorded_days"] != 7:
                raise ValueError("Selected week has missing or incomplete daily data")
            target = conn.execute("SELECT target_revenue,target_avg_enrolled_fte FROM weekly_targets "
                                  "WHERE center_id=? AND week_start=?",
                                  (self.assigned_center, str(start))).fetchone()
            previous = by_week.get(str(start - timedelta(weeks=1)))
            if previous and previous["recorded_days"] != 7:
                previous = None
            prior = [by_week.get(str(start - timedelta(weeks=i))) for i in range(1, 5)]
            complete = [r for r in prior if r is not None and r["recorded_days"] == 7]
            # Equal-weight mean of four weekly metrics; never silently use a shorter window.
            rolling = {}
            for metric in METRICS:
                values = [r[metric] for r in complete]
                rolling[metric] = (sum(values) / 4 if len(complete) == 4
                                   and all(v is not None for v in values) else None)
            target_values = dict(target) if target else None
            return {
                "center": dict(center), "reference_date": str(reference),
                "week_start": str(start), "week_end": str(end),
                "source": {"database": self.database.name, "view": "weekly_actuals",
                           "target_table": "weekly_targets",
                           "data_through": conn.execute("SELECT MAX(service_date) FROM daily_performance "
                                                       "WHERE center_id=?", (self.assigned_center,)).fetchone()[0]},
                "actuals": selected, "targets": target_values,
                "versus_target": {
                    "revenue": change(selected["actual_revenue"], target[0] if target else None),
                    "enrollment_fte": change(selected["avg_enrolled_fte"], target[1] if target else None)},
                "previous_week": {
                    "week_start": str(start - timedelta(weeks=1)), "available": previous is not None,
                    "actuals": previous,
                    "comparisons": {m: change(selected[m], previous[m] if previous else None) for m in METRICS}},
                "prior_four_weeks": {
                    "start": str(start - timedelta(weeks=4)), "end": str(start - timedelta(days=1)),
                    "complete_weeks": len(complete), "available": len(complete) == 4,
                    "method": "Equal-weight average of four complete weekly metrics; selected week excluded",
                    "averages": rolling,
                    "comparisons": {m: change(selected[m], rolling[m]) for m in METRICS}},
                "notes": ["Percent changes use percent units; staffed_occupancy uses a 0-to-1 fraction.",
                          "Raw revenue comparisons are not adjusted for different numbers of open days.",
                          "SQL identifies differences, not operational causes."]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assigned-center", required=True, help="Development identity simulation")
    parser.add_argument("--week-start", help="Sunday, YYYY-MM-DD; defaults to latest completed week")
    parser.add_argument("--database", type=Path, help="Defaults to the current rolling dataset")
    args = parser.parse_args()
    try:
        if args.database is None:
            try:
                from .runtime_data import active_data_dir
            except ImportError:
                from runtime_data import active_data_dir
            args.database = active_data_dir() / "center_performance.sqlite"
        result = CenterAnalytics(args.database, args.assigned_center).weekly_performance(args.week_start)
    except (ValueError, sqlite3.Error) as exc:
        parser.exit(2, f"Analytics error: {exc}\n")
    print(json.dumps(result, indent=2, allow_nan=False))
