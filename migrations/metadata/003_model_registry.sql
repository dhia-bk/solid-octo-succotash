-- 003_model_registry.sql
-- Purpose: ML model and analytics version run history for GDS algorithms and inference.
-- Unlocks: app/db/model_registry.py (ModelRegistryRepository), app/analytics/
-- Depends on: nothing
--
-- Column names mirror ModelRegistryRecord and the INSERT statement in model_registry.py exactly.
-- run_id is the PRIMARY KEY — one row per model run, not per model version.
-- status values: pending | running | succeeded | failed | deprecated
-- PostgreSQL note: TEXT columns may be typed VARCHAR; JSON columns may use JSONB type.

CREATE TABLE IF NOT EXISTS model_registry (
    run_id                      TEXT    NOT NULL PRIMARY KEY,   -- UUID run identifier
    model_type                  TEXT    NOT NULL,               -- e.g. leiden | pagerank | inference | weighting
    logical_version             TEXT    NOT NULL,               -- semver e.g. "1.0.0"
    config_version              TEXT,                           -- semver of config used; NULL if unversioned
    status                      TEXT    NOT NULL DEFAULT 'pending',
                                                                -- pending | running | succeeded | failed | deprecated
    artifact_uri                TEXT,                           -- path or URI to stored model artifact
    compatibility_metadata_json TEXT    NOT NULL DEFAULT '{}',  -- version compatibility metadata
    metrics_summary_json        TEXT    NOT NULL DEFAULT '{}',  -- evaluation metrics at registration
    created_at                  TEXT    NOT NULL,               -- ISO 8601 UTC; set at INSERT time
    updated_at                  TEXT    NOT NULL                -- ISO 8601 UTC; set on every UPDATE
);

CREATE INDEX IF NOT EXISTS idx_model_registry_model_type
    ON model_registry (model_type);

CREATE INDEX IF NOT EXISTS idx_model_registry_status
    ON model_registry (status);

CREATE INDEX IF NOT EXISTS idx_model_registry_created_at
    ON model_registry (created_at);

-- Composite index for the get_latest() query: model_type + status + created_at DESC
CREATE INDEX IF NOT EXISTS idx_model_registry_type_status_created
    ON model_registry (model_type, status, created_at);
