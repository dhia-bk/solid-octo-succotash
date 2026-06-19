-- 002_checkpoints.sql
-- Purpose: Per-source extraction watermarks for incremental pipeline runs.
-- Unlocks: app/db/checkpoints.py (CheckpointRepository)
-- Depends on: nothing (independent of job_runs)
--
-- Primary key is the composite (namespace, pipeline_name, source_name) triple,
-- matching the unique key assumed by the ON DUPLICATE KEY UPDATE upsert in
-- CheckpointRepository.upsert_checkpoint().
--
-- ON DUPLICATE KEY UPDATE is MySQL/MariaDB syntax. For SQLite compatibility the
-- application layer uses "INSERT OR REPLACE" or "INSERT ... ON CONFLICT DO UPDATE".
-- This migration creates the UNIQUE constraint that makes both dialects work.
--
-- Column names mirror CheckpointRecord and the SELECT/INSERT in checkpoints.py exactly.
-- PostgreSQL note: updated_at may use TIMESTAMP WITH TIME ZONE; TEXT is cross-dialect safe.

CREATE TABLE IF NOT EXISTS checkpoints (
    namespace               TEXT    NOT NULL,   -- logical namespace, e.g. "project_pulse"
    pipeline_name           TEXT    NOT NULL,   -- pipeline that owns this checkpoint
    source_name             TEXT    NOT NULL,   -- warehouse source table name
    checkpoint_strategy     TEXT    NOT NULL,   -- timestamp_watermark | numeric_watermark | full_refresh
    watermark_value         TEXT,               -- ISO timestamp or integer string; NULL for full_refresh
    last_successful_run_id  TEXT,               -- FK to job_runs.run_id (not enforced for SQLite compat)
    metadata_json           TEXT    NOT NULL DEFAULT '{}',
    updated_at              TEXT    NOT NULL,   -- ISO 8601 UTC; set on every upsert
    PRIMARY KEY (namespace, pipeline_name, source_name)
);

CREATE INDEX IF NOT EXISTS idx_checkpoints_pipeline_name
    ON checkpoints (pipeline_name);

CREATE INDEX IF NOT EXISTS idx_checkpoints_source_name
    ON checkpoints (source_name);

CREATE INDEX IF NOT EXISTS idx_checkpoints_last_successful_run_id
    ON checkpoints (last_successful_run_id);
