-- 001_job_runs.sql
-- Purpose: Pipeline and job run history, lifecycle status, and audit trail.
-- Unlocks: app/db/job_runs.py (JobRunRepository)
-- Depends on: nothing
--
-- Column names mirror JobRunRecord and the INSERT statement in job_runs.py exactly.
-- status values: pending | running | succeeded | failed | canceled
-- duration_ms: integer milliseconds (computed on finalize from started_at/finished_at)
-- PostgreSQL note: TEXT columns may be typed VARCHAR(255/64) for stricter schemas.

CREATE TABLE IF NOT EXISTS job_runs (
    run_id          TEXT    NOT NULL PRIMARY KEY,   -- UUID run identifier
    job_name        TEXT,                           -- logical job name (NULL for pipeline-only runs)
    pipeline_name   TEXT,                           -- logical pipeline name (NULL for job-only runs)
    status          TEXT    NOT NULL DEFAULT 'pending',
                                                    -- pending | running | succeeded | failed | canceled
    started_at      TEXT,                           -- ISO 8601 UTC; NULL until mark_running()
    finished_at     TEXT,                           -- ISO 8601 UTC; NULL while running
    duration_ms     INTEGER,                        -- wall-clock ms; NULL while running
    environment     TEXT,                           -- dev | staging | prod
    version         TEXT,                           -- app semver at run time
    error_message   TEXT,                           -- last error if status=failed/canceled
    metadata_json   TEXT    NOT NULL DEFAULT '{}',  -- arbitrary JSON for extended context
    created_at      TEXT    NOT NULL,               -- ISO 8601 UTC; set at INSERT time
    updated_at      TEXT    NOT NULL                -- ISO 8601 UTC; set on every UPDATE
);

CREATE INDEX IF NOT EXISTS idx_job_runs_pipeline_name
    ON job_runs (pipeline_name);

CREATE INDEX IF NOT EXISTS idx_job_runs_job_name
    ON job_runs (job_name);

CREATE INDEX IF NOT EXISTS idx_job_runs_status
    ON job_runs (status);

CREATE INDEX IF NOT EXISTS idx_job_runs_started_at
    ON job_runs (started_at);

CREATE INDEX IF NOT EXISTS idx_job_runs_environment
    ON job_runs (environment);
