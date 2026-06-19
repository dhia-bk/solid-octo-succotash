// 005_serving_views.cypher
// Purpose: Create serving view metadata nodes and GDS projection configurations.
// Unlocks: app/serving/ layer, app/analytics/graph_projection.py
// Depends on: 001_constraints.cypher, 002_indexes.cypher
//
// GDSProjectionConfig nodes store projection parameters so that
// app/analytics/graph_projection.py knows how to build each GDS named graph.
// These are NOT the projected graphs themselves — they are configuration records.
//
// ServingViewConfig nodes document the expected shape of serving-layer reads
// including required properties, relationship paths, and freshness SLAs.

// ── GDS projection configurations ─────────────────────────────────────────────

MERGE (proj:GDSProjectionConfig {name: 'hidden_tribes'})
SET proj.node_labels = ['User'],
    proj.relationship_types = ['MEMBER_OF', 'PREDICTED', 'HAS_AFFINITY'],
    proj.node_properties = ['tribe_id', 'pagerank_score'],
    proj.relationship_properties = ['activity_weight'],
    proj.orientation = 'UNDIRECTED',
    proj.created_at = datetime();

MERGE (proj:GDSProjectionConfig {name: 'user_engagement'})
SET proj.node_labels = ['User', 'Match', 'PrivateLeague'],
    proj.relationship_types = ['PREDICTED', 'MEMBER_OF'],
    proj.node_properties = ['tribe_id'],
    proj.relationship_properties = ['activity_weight'],
    proj.orientation = 'NATURAL',
    proj.created_at = datetime();

// ── Serving layer view configurations ─────────────────────────────────────────

MERGE (sv:ServingViewConfig {view_name: 'user_profile'})
SET sv.required_properties = ['id', 'country', 'current_subscription_name', 'is_suspended'],
    sv.relationship_paths = ['CURRENT_STATE', 'FAVORS', 'HAS_AFFINITY'],
    sv.freshness_max_hours = 24,
    sv.created_at = datetime();

MERGE (sv:ServingViewConfig {view_name: 'tribe_summary'})
SET sv.required_properties = ['tribe_id', 'member_count', 'dominant_topic', 'dominant_team'],
    sv.freshness_max_hours = 24,
    sv.created_at = datetime();

MERGE (sv:ServingViewConfig {view_name: 'prediction_context'})
SET sv.required_properties = ['id', 'prediction_count', 'accuracy_rate'],
    sv.freshness_max_hours = 6,
    sv.created_at = datetime();

MERGE (sv:ServingViewConfig {view_name: 'persona_state_snapshot'})
SET sv.required_properties = ['id', 'pcm_stage', 'behaviour_label', 'calculated_at'],
    sv.relationship_paths = ['HAS_STATE', 'PREVIOUS_STATE'],
    sv.freshness_max_hours = 24,
    sv.created_at = datetime();
