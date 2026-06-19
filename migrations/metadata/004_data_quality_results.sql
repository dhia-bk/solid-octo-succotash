-- 004_data_quality_results.sql
-- Purpose: Persist ValidationResult records for quality trend analysis.
-- Unlocks: app/validation/ persistence path, quality dashboards
-- Depends on: 001_job_runs.sql (run_id reference, not enforced in SQLite)
--
-- Maps ValidationResult fields from app/validation/base.py:
--   check_name → check_name
--   passed     → passed (bool → INTEGER: 1=passed, 0=failed)
--   severity   → severity (ValidationSeverity enum → TEXT)
--   source     → source_name (more descriptive as a SQL column; mapper sets this)
--   message    → message
--   details    → details_json (dict serialized to JSON)
--   run_id     → run_id
--   checked_at → checked_at
--
-- PostgreSQL note: passed may use BOOLEAN; details_json may use JSONB.

CREATE TABLE IF NOT EXISTS data_quality_results (
    id          TEXT    NOT NULL PRIMARY KEY,   -- UUID
    run_id      TEXT    NOT NULL,               -- FK to job_runs.run_id
    check_name  TEXT    NOT NULL,
    source_name TEXT    NOT NULL,               -- ValidationResult.source
    passed      INTEGER NOT NULL,               -- 1=passed, 0=failed
    severity    TEXT    NOT NULL,               -- critical | error | warning | info
    message     TEXT    NOT NULL,
    details_json TEXT   NOT NULL DEFAULT '{}',  -- serialized ValidationResult.details dict
    checked_at  TEXT    NOT NULL                -- ISO 8601 UTC
);

CREATE INDEX IF NOT EXISTS idx_dqr_run_id
    ON data_quality_results (run_id);

CREATE INDEX IF NOT EXISTS idx_dqr_source_name
    ON data_quality_results (source_name);

CREATE INDEX IF NOT EXISTS idx_dqr_check_name
    ON data_quality_results (check_name);

CREATE INDEX IF NOT EXISTS idx_dqr_severity
    ON data_quality_results (severity);

CREATE INDEX IF NOT EXISTS idx_dqr_passed
    ON data_quality_results (passed);

-- Aggregated quality summary per run (materialized for fast dashboard queries).
-- Populated and updated by the validation persistence layer after each run.
CREATE TABLE IF NOT EXISTS data_quality_run_summary (
    run_id          TEXT    NOT NULL PRIMARY KEY,   -- FK to job_runs.run_id
    source_name     TEXT,                           -- NULL for pipeline-level summaries
    total_checks    INTEGER NOT NULL DEFAULT 0,
    passed_count    INTEGER NOT NULL DEFAULT 0,
    failed_count    INTEGER NOT NULL DEFAULT 0,
    critical_count  INTEGER NOT NULL DEFAULT 0,
    error_count     INTEGER NOT NULL DEFAULT 0,
    warning_count   INTEGER NOT NULL DEFAULT 0,
    summarized_at   TEXT    NOT NULL                -- ISO 8601 UTC
);
