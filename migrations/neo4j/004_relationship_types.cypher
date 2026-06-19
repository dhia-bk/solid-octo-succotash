// 004_relationship_types.cypher
// Purpose: Register all expected relationship types in a graph metadata node.
//          Used for schema audit and relationship coverage checks.
// Unlocks: app/validation/source_coverage_checks.py relationship checks
// Depends on: 003_node_labels.cypher
//
// The type list mirrors GRAPH_RELATIONSHIP_TYPES in app/core/constants.py exactly.
// This migration creates no schema objects — it writes a single GraphSchemaMeta node.

MERGE (meta:GraphSchemaMeta {schema_type: 'relationship_types'})
SET meta.types = [
    'EQUIPPED', 'AWARDED', 'FAVORS',
    'PLAYS_IN', 'HOME_TEAM', 'AWAY_TEAM', 'IN_LEAGUE', 'PLAYED_IN',
    'MEMBER_OF', 'HAS_THEME', 'PROMOTES',
    'POSTED', 'COMMENTED', 'REPLIES_TO', 'JOINED_DISCUSSION', 'DIRECT_MESSAGE',
    'PREDICTED', 'CHALLENGED', 'PARTICIPATED_IN', 'HAS_FIXTURE', 'ABOUT',
    'EXHIBITS', 'CURRENT_STATE', 'PREVIOUS_STATE', 'HAS_STATE',
    'DISCUSSED', 'EXPRESSED', 'HAS_AFFINITY', 'HAS_RATING',
    'TALKED_TO', 'HAS_MESSAGE', 'USED_TOOL',
    'SPENT', 'PURCHASED', 'REDEEMED', 'SUBSCRIBED_TO', 'ACHIEVED',
    'HAS_TAG', 'RECEIVED_NOTIFICATION', 'MODERATED', 'GENERATED_FOR',
    'LIKED', 'ANSWERED', 'FRIENDED'
],
meta.type_count = 44,
meta.registered_at = datetime(),
meta.schema_version = '1.0.0';
