// 006_graph_metadata.cypher
// Purpose: Graph-native pipeline metadata, schema versioning, and source sync state.
// Unlocks: graph-native audit queries, pipeline run tracking in graph,
//          freshness checks without hitting the metadata DB
// Depends on: 001_constraints.cypher through 005_serving_views.cypher
//
// PipelineRun nodes are created by loaders at runtime; this migration defines
// the constraint and index so MERGE operations are safe from the first run.
//
// SourceSyncState nodes provide graph-native freshness checks. One node per source,
// updated by the loader on each successful run. Stub nodes are seeded here for
// all declared graph-emitting sources so freshness queries never return null.

// ── Graph schema version ───────────────────────────────────────────────────────

MERGE (v:GraphSchemaVersion {version: '1.0.0'})
SET v.applied_at = datetime(),
    v.description = 'Initial schema: all node types, constraints, indexes, and serving configs',
    v.migration_files = [
        '001_constraints.cypher',
        '002_indexes.cypher',
        '003_node_labels.cypher',
        '004_relationship_types.cypher',
        '005_serving_views.cypher',
        '006_graph_metadata.cypher'
    ];

// ── PipelineRun constraint and indexes ────────────────────────────────────────

CREATE CONSTRAINT pipeline_run_id_unique IF NOT EXISTS
    FOR (n:PipelineRun) REQUIRE n.run_id IS UNIQUE;

CREATE INDEX pipeline_run_started_at IF NOT EXISTS
    FOR (n:PipelineRun) ON (n.started_at);

CREATE INDEX pipeline_run_source_name IF NOT EXISTS
    FOR (n:PipelineRun) ON (n.source_name);

// ── SourceSyncState constraint ────────────────────────────────────────────────

CREATE CONSTRAINT source_sync_state_unique IF NOT EXISTS
    FOR (n:SourceSyncState) REQUIRE n.source_name IS UNIQUE;

// ── Seed stub SourceSyncState nodes ──────────────────────────────────────────
// One node per graph-emitting source. Loaders MERGE against source_name and
// SET last_synced_at, last_run_id, last_row_count on each successful run.
// These stubs ensure freshness queries return a row rather than null for
// sources that have never been loaded.

FOREACH (source IN [
    'dim_users',
    'dim_teams',
    'dim_leagues',
    'dim_fixtures',
    'dim_private_leagues',
    'dim_league_themes',
    'dim_influencer_leagues',
    'dim_posts',
    'dim_comments',
    'fct_predictions',
    'fct_user_behavior',
    'fct_topics',
    'fct_sentiment',
    'fct_chatbot_conversations',
    'fct_coin_transactions',
    'fct_duels',
    'fct_moderation_events'
] |
    MERGE (s:SourceSyncState {source_name: source})
    ON CREATE SET
        s.last_synced_at = null,
        s.last_run_id    = null,
        s.last_row_count = null,
        s.status         = 'never_synced'
);
