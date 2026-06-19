-- 005_source_inventory.sql
-- Purpose: Warehouse source registration, inclusion decisions, and pipeline metadata.
-- Unlocks: app/source_inventory/registry.py, source coverage checks
-- Depends on: nothing
--
-- inclusion_mode values from SOURCE_INCLUSION_CATEGORIES in app/core/constants.py:
--   graph_core | graph_enrichment | serving_only | feature_source | excluded
--
-- PostgreSQL note: has_pii / has_incremental may use BOOLEAN; TEXT may use VARCHAR.

CREATE TABLE IF NOT EXISTS source_inventory (
    id                      TEXT    NOT NULL PRIMARY KEY,   -- UUID
    source_name             TEXT    NOT NULL UNIQUE,        -- logical warehouse table name
    inclusion_mode          TEXT    NOT NULL,               -- graph_core | graph_enrichment | serving_only | feature_source | excluded
    graph_entity_mappings   TEXT,                           -- comma-separated graph labels/rel types
    freshness_field         TEXT,                           -- watermark column name in the source
    primary_keys            TEXT,                           -- comma-separated PK field names
    extractor_class         TEXT,                           -- fully-qualified extractor class name
    transformer_class       TEXT,                           -- fully-qualified transformer class name
    row_class               TEXT,                           -- fully-qualified row dataclass name
    domain                  TEXT,                           -- identity | sports | social | intelligence | etc.
    has_pii                 INTEGER NOT NULL DEFAULT 0,     -- 1=contains PII, 0=no PII
    has_incremental         INTEGER NOT NULL DEFAULT 0,     -- 1=supports incremental extraction, 0=full refresh only
    registered_at           TEXT    NOT NULL,               -- ISO 8601 UTC
    last_seen_at            TEXT,                           -- ISO 8601 UTC of last successful extraction
    notes                   TEXT
);

CREATE INDEX IF NOT EXISTS idx_source_inventory_inclusion_mode
    ON source_inventory (inclusion_mode);

CREATE INDEX IF NOT EXISTS idx_source_inventory_domain
    ON source_inventory (domain);

-- Lightweight per-source per-run history for operational dashboards.
CREATE TABLE IF NOT EXISTS source_run_history (
    id              TEXT    NOT NULL PRIMARY KEY,   -- UUID
    source_name     TEXT    NOT NULL,               -- FK to source_inventory.source_name
    run_id          TEXT    NOT NULL,               -- FK to job_runs.run_id
    row_count       INTEGER,
    watermark_value TEXT,
    duration_ms     INTEGER,                        -- wall-clock ms for this source in the run
    status          TEXT    NOT NULL,               -- completed | failed | skipped
    run_at          TEXT    NOT NULL                -- ISO 8601 UTC
);

CREATE INDEX IF NOT EXISTS idx_source_run_history_source_name
    ON source_run_history (source_name);

CREATE INDEX IF NOT EXISTS idx_source_run_history_run_id
    ON source_run_history (run_id);
