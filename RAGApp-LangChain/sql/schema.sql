PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS centers (
    center_id TEXT PRIMARY KEY,
    center_name TEXT NOT NULL,
    region TEXT NOT NULL,
    licensed_capacity INTEGER NOT NULL CHECK (licensed_capacity > 0)
);

CREATE TABLE IF NOT EXISTS daily_performance (
    center_id TEXT NOT NULL REFERENCES centers(center_id),
    service_date TEXT NOT NULL CHECK (date(service_date) IS NOT NULL),
    is_open INTEGER NOT NULL CHECK (is_open IN (0, 1)),
    enrolled_fte REAL NOT NULL CHECK (enrolled_fte >= 0),
    staffed_capacity INTEGER NOT NULL CHECK (staffed_capacity >= 0),
    earned_tuition_revenue REAL NOT NULL CHECK (earned_tuition_revenue >= 0),
    inquiries INTEGER NOT NULL CHECK (inquiries >= 0),
    tours INTEGER NOT NULL CHECK (tours >= 0),
    new_enrollments INTEGER NOT NULL CHECK (new_enrollments >= 0),
    withdrawals INTEGER NOT NULL CHECK (withdrawals >= 0),
    waitlist_count INTEGER NOT NULL CHECK (waitlist_count >= 0),
    PRIMARY KEY (center_id, service_date),
    CHECK (is_open = 1 OR (staffed_capacity = 0 AND earned_tuition_revenue = 0))
);

CREATE TABLE IF NOT EXISTS weekly_targets (
    center_id TEXT NOT NULL REFERENCES centers(center_id),
    week_start TEXT NOT NULL CHECK (date(week_start) IS NOT NULL AND strftime('%w', week_start) = '0'),
    target_revenue REAL NOT NULL CHECK (target_revenue >= 0),
    target_avg_enrolled_fte REAL NOT NULL CHECK (target_avg_enrolled_fte >= 0),
    PRIMARY KEY (center_id, week_start)
);

CREATE TABLE IF NOT EXISTS document_manifest (
    document_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    document_type TEXT NOT NULL,
    center_id TEXT REFERENCES centers(center_id),
    week_start TEXT CHECK (week_start IS NULL OR (date(week_start) IS NOT NULL AND strftime('%w', week_start) = '0')),
    effective_from TEXT NOT NULL CHECK (date(effective_from) IS NOT NULL),
    effective_to TEXT CHECK (effective_to IS NULL OR date(effective_to) IS NOT NULL),
    version INTEGER NOT NULL CHECK (version > 0),
    source_path TEXT NOT NULL,
    CHECK (effective_to IS NULL OR effective_to >= effective_from)
);

CREATE VIEW IF NOT EXISTS weekly_actuals AS
SELECT
    center_id,
    date(service_date, '-' || strftime('%w', service_date) || ' days') AS week_start,
    COUNT(*) AS recorded_days,
    SUM(is_open) AS open_days,
    SUM(earned_tuition_revenue) AS actual_revenue,
    AVG(CASE WHEN is_open = 1 THEN enrolled_fte END) AS avg_enrolled_fte,
    AVG(CASE WHEN is_open = 1 THEN staffed_capacity END) AS avg_staffed_capacity,
    SUM(CASE WHEN is_open = 1 THEN enrolled_fte ELSE 0 END)
        / NULLIF(SUM(CASE WHEN is_open = 1 THEN staffed_capacity ELSE 0 END), 0) AS staffed_occupancy,
    SUM(inquiries) AS inquiries,
    SUM(tours) AS tours,
    SUM(new_enrollments) AS new_enrollments,
    SUM(withdrawals) AS withdrawals
FROM daily_performance
GROUP BY center_id, week_start;
