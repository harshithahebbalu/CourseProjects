"""Generate a deterministic, fictional dataset using only the Python standard library."""

import argparse
import hashlib
import json
import math
import random
import sqlite3
from datetime import date, timedelta
from pathlib import Path

try:
    from .reporting import runtime_date, dataset_window, synthetic_holidays
except ImportError:
    from reporting import runtime_date, dataset_window, synthetic_holidays

ROOT = Path(__file__).resolve().parents[2]
SEED = 1042026
NAMES = ["Maple Grove", "Willow Creek", "Cedar Hill", "Sunny Meadow", "Oak Trail",
         "Birch Valley", "Pine Ridge", "Elm Garden", "Aspen Brook", "Juniper Park"]
SCENARIOS = {
    "C001": ("Staffed capacity constraint", "A teacher vacancy has kept one classroom unavailable. "
             "Families remain on the waitlist; confirm age-group fit and staffing readiness before offering seats."),
    "C002": ("Lower realized tuition", "Temporary tuition discounts are active for several families. "
             "Enrollment is stable; review discount approvals and expiration dates against the tuition register."),
    "C003": ("Weaker enrollment pipeline", "Tour activity has slowed and recent withdrawals exceed new starts. "
             "A nearby competitor is mentioned in inquiry feedback; review follow-up activity before drawing conclusions."),
}

GUIDANCE = {
    "kpi_definitions": ("KPI definitions", "Revenue is earned tuition for a service date, not cash received. "
        "Enrollment is active enrolled full-time-equivalent (FTE) seats. Weekly enrollment averages open days. "
        "Revenue variance equals actual minus target; percentage variance divides by target and is undefined at zero. "
        "Staffed occupancy divides the sum of open-day enrolled FTE by the sum of open-day staffed capacity. "
        "New enrollments and withdrawals count children, not FTE; they cannot directly reconcile FTE balances. "
        "Targets are approved planning assumptions. Previous-four-week comparisons exclude the selected week."),
    "enrollment_playbook": ("Enrollment follow-up playbook", "Review inquiry and tour follow-up weekly. "
        "Check the reasons families defer or decline enrollment and record the next follow-up date. "
        "Compare waitlisted age groups and requested schedules with actual classroom availability. "
        "Center-level vacancies alone do not establish that a particular child can be enrolled."),
    "capacity_playbook": ("Staffed capacity review playbook", "Licensed capacity is an upper limit, not an offer of seats. "
        "Confirm staffing readiness, classroom availability, age-group constraints, and required approvals "
        "with the operations team before changing staffed capacity. Never recommend exceeding applicable ratios. "
        "This fictional playbook does not supply jurisdiction-specific staffing rules."),
    "discount_policy": ("Synthetic discount review policy", "Document an approval, start date, and expiration date "
        "for each tuition discount. Review active discounts weekly and escalate missing approvals to Finance. "
        "Do not automatically remove discounts or change family tuition based on a copilot recommendation."),
}


def document(conn, output, doc_id, title, body, center=None, week=None, effective_from=None):
    relative = Path("documents") / f"{doc_id}.md"
    effective = str(week or effective_from)
    content = (f"# {title}\n\nSYNTHETIC TRAINING DATA — not a real company report.\n\n"
               f"Document ID: {doc_id}\nCenter: {center or 'Shared'}\n"
               f"Effective from: {effective}\nVersion: 1\n\n{body}\n")
    (output / relative).write_text(content, encoding="utf-8")
    conn.execute("INSERT INTO document_manifest VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                 (doc_id, title, "weekly_report" if week else "guidance", center,
                  str(week) if week else None, effective, None, 1, relative.as_posix()))


def validate(conn, output, start, end):
    def require(condition, message):
        if not condition:
            raise ValueError(message)

    require(conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok", "SQLite integrity")
    require(not conn.execute("PRAGMA foreign_key_check").fetchall(), "Foreign keys")
    require(conn.execute("SELECT COUNT(*) FROM daily_performance").fetchone()[0] == 3640, "Daily count")
    weeks = conn.execute("SELECT * FROM weekly_actuals").fetchall()
    require(len(weeks) == 520 and all(w[2] == 7 for w in weeks), "Complete reporting weeks")
    require(conn.execute("SELECT MIN(service_date), MAX(service_date) FROM daily_performance").fetchone()
            == (str(start), str(end)), "Date range")
    require(not conn.execute("SELECT 1 FROM daily_performance d JOIN centers c USING(center_id) "
                             "WHERE d.enrolled_fte > c.licensed_capacity "
                             "OR d.staffed_capacity > c.licensed_capacity "
                             "OR (d.is_open=1 AND d.enrolled_fte>d.staffed_capacity)").fetchall(), "Capacity bounds")
    require(conn.execute("SELECT COUNT(*) FROM weekly_targets").fetchone()[0] == 520, "Targets")
    manifests = conn.execute("SELECT source_path FROM document_manifest").fetchall()
    require(len(manifests) == 524 and all((output / p[0]).is_file() for p in manifests), "Documents")
    # Independently recompute latest-week aggregates from daily rows (not the SQL view).
    for center, *_ in conn.execute("SELECT * FROM centers"):
        rows = conn.execute("SELECT is_open,enrolled_fte,staffed_capacity,earned_tuition_revenue "
                            "FROM daily_performance WHERE center_id=? AND service_date BETWEEN ? AND ?",
                            (center, str(end - timedelta(days=6)), str(end))).fetchall()
        actual = conn.execute("SELECT actual_revenue,avg_enrolled_fte,staffed_occupancy FROM weekly_actuals "
                              "WHERE center_id=? AND week_start=?", (center, str(end - timedelta(days=6)))).fetchone()
        opened = [r for r in rows if r[0]]
        expected = (sum(r[3] for r in rows), sum(r[1] for r in opened) / len(opened),
                    sum(r[1] for r in opened) / sum(r[2] for r in opened))
        require(all(math.isclose(a, b, abs_tol=1e-8) for a, b in zip(actual, expected)), "Weekly arithmetic")


def generate(output, reference_date=None):
    reference = reference_date or runtime_date()
    start, end = dataset_window(reference)
    holidays = synthetic_holidays(start, end)
    output.mkdir(parents=True, exist_ok=True)
    db = output / "center_performance.sqlite"
    if db.exists() or (output / "documents").exists():
        raise FileExistsError("Output already contains generated artifacts; use a new --output directory.")
    (output / "documents").mkdir()
    rng = random.Random(SEED)
    conn = sqlite3.connect(db)
    try:
        conn.executescript((ROOT / "sql/schema.sql").read_text(encoding="utf-8"))
        for index, name in enumerate(NAMES):
            center = f"C{index + 1:03}"
            capacity = 100 + (index % 3) * 10
            staffed = capacity - 5
            planned_fte = round(capacity * .82, 1)
            rate = 85 + index * 2
            conn.execute("INSERT INTO centers VALUES (?, ?, ?, ?)",
                         (center, name, "North" if index < 5 else "South", capacity))
            for wi in range(52):
                week = start + timedelta(weeks=wi)
                operating_dates = [week + timedelta(days=d) for d in range(7)
                                   if (week + timedelta(days=d)).weekday() < 5
                                   and week + timedelta(days=d) not in holidays]
                conn.execute("INSERT INTO weekly_targets VALUES (?, ?, ?, ?)",
                             (center, str(week), round(planned_fte * rate * len(operating_dates), 2), planned_fte))
                active = center in SCENARIOS and wi >= 48
                available = staffed - (25 if active and center == "C001" else 0)
                baseline = planned_fte + 1.5 * math.sin(wi / 6) + rng.uniform(-1, 1)
                if active and center == "C001":
                    baseline = available - 2
                elif active and center == "C003":
                    baseline -= 4 * (wi - 47)
                for day in range(7):
                    service = week + timedelta(days=day)
                    is_open = int(service in operating_dates)
                    fte = round(max(0, min(available, baseline)), 1)
                    daily_rate = rate * (.9 if active and center == "C002" else 1)
                    inquiries = rng.randint(1, 5) if is_open else 0
                    tours = rng.randint(0, 2) if is_open else 0
                    starts = int(is_open and day == 1 and wi % 2 == 0)
                    exits = int(is_open and day == 5 and wi % 3 == 0)
                    if active and center == "C003":
                        inquiries, tours, starts = (int(is_open), 0, 0)
                        exits = int(is_open and day in (2, 4))
                    waitlist = 18 if active and center == "C001" else 3 + index % 5
                    conn.execute("INSERT INTO daily_performance VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                                 (center, str(service), is_open, fte, available if is_open else 0,
                                  round(fte * daily_rate, 2) if is_open else 0,
                                  inquiries, tours, starts, exits, waitlist))
                actual = conn.execute("SELECT actual_revenue,avg_enrolled_fte,avg_staffed_capacity,"
                                      "inquiries,tours,new_enrollments,withdrawals FROM weekly_actuals "
                                      "WHERE center_id=? AND week_start=?", (center, str(week))).fetchone()
                note = SCENARIOS[center][1] if active else (
                    "No exceptional operating condition was recorded in this week's synthetic review. "
                    "Routine variation alone does not establish a cause; review detailed activity if performance is below plan.")
                body = (f"## Reporting period\n{week} through {week + timedelta(days=6)} (Sunday–Saturday).\n\n"
                        f"## Performance snapshot\nEarned tuition revenue: ${actual[0]:,.2f}.\n"
                        f"Average enrolled FTE: {actual[1]:.2f}. Average staffed capacity: {actual[2]:.2f}.\n"
                        f"Inquiries: {actual[3]}; tours: {actual[4]}; new enrollments: {actual[5]}; withdrawals: {actual[6]}.\n\n"
                        f"## Director observations\n{note}\n\n"
                        "## Follow-up\nCompare SQL actuals with approved weekly targets. Verify reported conditions "
                        "before attributing a financial variance to them; consult the applicable shared playbook.")
                document(conn, output, f"{center}_{week}", f"{name}: weekly operating report", body, center, week)
        for key, (title, body) in GUIDANCE.items():
            document(conn, output, key, title, body, effective_from=start)
        validate(conn, output, start, end)
        conn.commit()
        conn.row_factory = sqlite3.Row
        latest = [dict(r) for r in conn.execute(
            "SELECT a.center_id,a.week_start,a.actual_revenue,t.target_revenue,"
            "a.actual_revenue-t.target_revenue AS revenue_variance,a.avg_enrolled_fte,"
            "t.target_avg_enrolled_fte,a.staffed_occupancy FROM weekly_actuals a "
            "JOIN weekly_targets t USING(center_id,week_start) WHERE a.week_start=? ORDER BY a.center_id",
            (str(end - timedelta(days=6)),))]
        summary = {"reference_date": str(reference), "start": str(start), "end": str(end),
                   "seed": SEED, "centers": 10, "daily_records": 3640, "weekly_reports": 520,
                   "shared_documents": 4, "latest_week": latest,
                   "scenario_labels": {k: v[0] for k, v in SCENARIOS.items()}}
        (output / "generation_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        hashes = {p.relative_to(output).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in sorted((output / "documents").glob("*.md"))}
        (output / "document_hashes.json").write_text(json.dumps(hashes, indent=2), encoding="utf-8")
        print(f"Validated: 10 centers, 3,640 daily records, 520 complete weeks, 524 documents.\nOutput: {output}")
        for row in latest[:3]:
            print(f"{row['center_id']}: latest-week revenue variance ${row['revenue_variance']:,.2f}")
    finally:
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "data")
    parser.add_argument("--reference-date", type=date.fromisoformat, help="Optional fixed date for reproducible fixtures; defaults to today's Los Angeles date")
    args = parser.parse_args()
    generate(args.output.resolve(), reference_date=args.reference_date)
