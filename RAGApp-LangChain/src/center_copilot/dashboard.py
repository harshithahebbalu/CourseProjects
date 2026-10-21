"""Read-only dashboard data; these functions do not call a language model."""

import sqlite3
from contextlib import closing
from datetime import date, timedelta
from pathlib import Path

from .reporting import runtime_date


def connect(database):
    conn = sqlite3.connect(Path(database).resolve().as_uri() + "?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def center_options(database):
    with closing(connect(database)) as conn:
        return [dict(r) for r in conn.execute("SELECT center_id,center_name FROM centers ORDER BY center_id")]


def completed_weeks(database, center, reference_date=None):
    reference = reference_date or runtime_date()
    with closing(connect(database)) as conn:
        rows = conn.execute("SELECT week_start FROM weekly_actuals WHERE center_id=? AND recorded_days=7 "
                            "ORDER BY week_start DESC", (center,)).fetchall()
    return [r[0] for r in rows if date.fromisoformat(r[0]) + timedelta(days=6) < reference]


def revenue_trend(database, center, week_start):
    first = date.fromisoformat(week_start) - timedelta(weeks=7)
    with closing(connect(database)) as conn:
        return [dict(r) for r in conn.execute(
            "SELECT a.week_start,a.actual_revenue,t.target_revenue FROM weekly_actuals a "
            "LEFT JOIN weekly_targets t USING(center_id,week_start) "
            "WHERE a.center_id=? AND a.recorded_days=7 AND a.week_start BETWEEN ? AND ? ORDER BY a.week_start",
            (center, str(first), week_start))]
