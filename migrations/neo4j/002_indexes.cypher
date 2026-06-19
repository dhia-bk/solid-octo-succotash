// 002_indexes.cypher
// Purpose: Property indexes for query performance on high-cardinality filter axes.
// Unlocks: efficient loader MERGE queries, GDS projection filtering, serving layer reads
// Depends on: 001_constraints.cypher (labels must be established before indexing)
//
// IMPORTANT: Index names and property names here must match exactly the
// _LOOKUP_INDEXES list in app/schemas/graph/constraints.py.
// build_index_cypher() generates these statements from that module.
//
// Neo4j 5.x RANGE indexes are the default. TEXT indexes use CREATE TEXT INDEX syntax.

// ── User ──────────────────────────────────────────────────────────────────────

CREATE INDEX idx_user_country IF NOT EXISTS
    FOR (n:User) ON (n.country);

CREATE INDEX idx_user_gender IF NOT EXISTS
    FOR (n:User) ON (n.gender);

CREATE INDEX idx_user_subscription IF NOT EXISTS
    FOR (n:User) ON (n.current_subscription_name);

CREATE INDEX idx_user_suspended IF NOT EXISTS
    FOR (n:User) ON (n.is_suspended);

// ── Match ─────────────────────────────────────────────────────────────────────

CREATE INDEX idx_match_kickoff_at IF NOT EXISTS
    FOR (n:Match) ON (n.kickoff_at);

CREATE INDEX idx_match_status IF NOT EXISTS
    FOR (n:Match) ON (n.status);

// ── Content ───────────────────────────────────────────────────────────────────

CREATE INDEX idx_post_published_at IF NOT EXISTS
    FOR (n:Post) ON (n.published_at);

CREATE INDEX idx_comment_created_at IF NOT EXISTS
    FOR (n:Comment) ON (n.created_at);

// ── Intelligence ──────────────────────────────────────────────────────────────

CREATE INDEX idx_topic_label IF NOT EXISTS
    FOR (n:Topic) ON (n.topic_label);

CREATE INDEX idx_sentiment_label IF NOT EXISTS
    FOR (n:Sentiment) ON (n.sentiment_label);

CREATE INDEX idx_persona_state_pcm_stage IF NOT EXISTS
    FOR (n:PersonaState) ON (n.pcm_stage);

// ── AI / Communication ────────────────────────────────────────────────────────

CREATE INDEX idx_chatbot_conversation_start IF NOT EXISTS
    FOR (n:ChatbotConversation) ON (n.conversation_start);

// ── Moderation ────────────────────────────────────────────────────────────────

CREATE INDEX idx_moderation_event_at IF NOT EXISTS
    FOR (n:ModerationEvent) ON (n.event_at);

// ── Tags ──────────────────────────────────────────────────────────────────────

CREATE INDEX idx_tag_name IF NOT EXISTS
    FOR (n:Tag) ON (n.tag_name);

CREATE INDEX idx_tag_trending IF NOT EXISTS
    FOR (n:Tag) ON (n.is_trending);
