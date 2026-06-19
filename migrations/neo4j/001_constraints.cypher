// 001_constraints.cypher
// Purpose: Uniqueness constraints on all node types.
// Unlocks: loaders (MERGE queries require constraints for idempotency),
//          app/validation/graph_checks.py (constraint verification)
// Depends on: nothing
//
// IMPORTANT: These constraints are the migration-file representation of the
// CONSTRAINT_DECLARATIONS in app/schemas/graph/constraints.py.
// Every constraint name (e.g. unique_user_id) and property (n.id) must match
// exactly what build_constraint_cypher() generates from that module.
//
// All node types use the canonical `id` property as their uniqueness key.
// Domain-specific ID field names (user_id, fixture_id, etc.) are stored as
// additional properties; `id` is the graph-level primary key set by loaders.

// ── Identity ──────────────────────────────────────────────────────────────────

CREATE CONSTRAINT unique_user_id IF NOT EXISTS
    FOR (n:User) REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT unique_avatar_id IF NOT EXISTS
    FOR (n:Avatar) REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT unique_badge_id IF NOT EXISTS
    FOR (n:Badge) REQUIRE n.id IS UNIQUE;

// ── Sports ────────────────────────────────────────────────────────────────────

CREATE CONSTRAINT unique_team_id IF NOT EXISTS
    FOR (n:Team) REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT unique_league_id IF NOT EXISTS
    FOR (n:League) REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT unique_match_id IF NOT EXISTS
    FOR (n:Match) REQUIRE n.id IS UNIQUE;

// ── Private Leagues ───────────────────────────────────────────────────────────

CREATE CONSTRAINT unique_private_league_id IF NOT EXISTS
    FOR (n:PrivateLeague) REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT unique_league_theme_id IF NOT EXISTS
    FOR (n:LeagueTheme) REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT unique_influencer_league_id IF NOT EXISTS
    FOR (n:InfluencerLeague) REQUIRE n.id IS UNIQUE;

// ── Social ────────────────────────────────────────────────────────────────────

CREATE CONSTRAINT unique_post_id IF NOT EXISTS
    FOR (n:Post) REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT unique_comment_id IF NOT EXISTS
    FOR (n:Comment) REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT unique_discussion_id IF NOT EXISTS
    FOR (n:Discussion) REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT unique_prediction_discussion_id IF NOT EXISTS
    FOR (n:PredictionDiscussion) REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT unique_conversation_id IF NOT EXISTS
    FOR (n:Conversation) REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT unique_direct_pair_id IF NOT EXISTS
    FOR (n:DirectPair) REQUIRE n.id IS UNIQUE;

// ── Intelligence ──────────────────────────────────────────────────────────────

CREATE CONSTRAINT unique_persona_state_id IF NOT EXISTS
    FOR (n:PersonaState) REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT unique_topic_id IF NOT EXISTS
    FOR (n:Topic) REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT unique_sentiment_id IF NOT EXISTS
    FOR (n:Sentiment) REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT unique_rating_snapshot_id IF NOT EXISTS
    FOR (n:RatingSnapshot) REQUIRE n.id IS UNIQUE;

// ── AI ────────────────────────────────────────────────────────────────────────

CREATE CONSTRAINT unique_chatbot_conversation_id IF NOT EXISTS
    FOR (n:ChatbotConversation) REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT unique_chatbot_message_id IF NOT EXISTS
    FOR (n:ChatbotMessage) REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT unique_tool_call_id IF NOT EXISTS
    FOR (n:ToolCall) REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT unique_tool_id IF NOT EXISTS
    FOR (n:Tool) REQUIRE n.id IS UNIQUE;

// ── Economy ───────────────────────────────────────────────────────────────────

CREATE CONSTRAINT unique_coin_transaction_id IF NOT EXISTS
    FOR (n:CoinTransaction) REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT unique_voucher_id IF NOT EXISTS
    FOR (n:Voucher) REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT unique_partner_reward_id IF NOT EXISTS
    FOR (n:PartnerReward) REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT unique_subscription_product_id IF NOT EXISTS
    FOR (n:SubscriptionProduct) REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT unique_achievement_id IF NOT EXISTS
    FOR (n:Achievement) REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT unique_financial_event_id IF NOT EXISTS
    FOR (n:FinancialEvent) REQUIRE n.id IS UNIQUE;

// ── Competition ───────────────────────────────────────────────────────────────

CREATE CONSTRAINT unique_duel_id IF NOT EXISTS
    FOR (n:Duel) REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT unique_super6_round_id IF NOT EXISTS
    FOR (n:Super6Round) REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT unique_lms_competition_id IF NOT EXISTS
    FOR (n:LMSCompetition) REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT unique_poll_id IF NOT EXISTS
    FOR (n:Poll) REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT unique_question_id IF NOT EXISTS
    FOR (n:Question) REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT unique_quiz_id IF NOT EXISTS
    FOR (n:Quiz) REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT unique_quiz_question_id IF NOT EXISTS
    FOR (n:QuizQuestion) REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT unique_tag_id IF NOT EXISTS
    FOR (n:Tag) REQUIRE n.id IS UNIQUE;

// ── Ops / Content ─────────────────────────────────────────────────────────────

CREATE CONSTRAINT unique_notification_content_id IF NOT EXISTS
    FOR (n:NotificationContent) REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT unique_moderation_event_id IF NOT EXISTS
    FOR (n:ModerationEvent) REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT unique_ai_article_id IF NOT EXISTS
    FOR (n:AIArticle) REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT unique_news_id IF NOT EXISTS
    FOR (n:News) REQUIRE n.id IS UNIQUE;
