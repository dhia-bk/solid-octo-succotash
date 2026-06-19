"""
Runtime source registry for Project Pulse Knowledge Graph.

This file is the single authoritative list of every warehouse table:
- its domain grouping
- its inclusion mode
- its primary keys
- its freshness field for incremental watermarking
- its graph entity mappings
- a brief rationale note

Design rules:
- This file is the ground truth. The metadata DB holds a mirrored copy.
- If the two diverge, the code is correct and the DB is stale.
- No later module should hardcode table inclusion decisions independently.
- All access should go through the helper functions at the bottom.
- sync_registry_to_db() is the only function with side effects. It is safe
  to import this module without touching any external system.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.core.constants import (
    ACHIEVED,
    ACHIEVEMENT,
    AI_ARTICLE,
    AVATAR,
    BADGE,
    CHATBOT_CONVERSATION,
    CHATBOT_MESSAGE,
    COIN_TRANSACTION,
    COMMENT,
    CONVERSATION,
    DIRECT_PAIR,
    DISCUSSION,
    DUEL,
    EXCLUDED,
    FEATURE_SOURCE,
    FINANCIAL_EVENT,
    GRAPH_CORE,
    GRAPH_ENRICHMENT,
    HAS_AFFINITY,
    HAS_FIXTURE,
    INFLUENCER_LEAGUE,
    JOINED_DISCUSSION,
    LEAGUE,
    LEAGUE_THEME,
    LMS_COMPETITION,
    MATCH,
    MEMBER_OF,
    MODERATION_EVENT,
    NEWS,
    NOTIFICATION_CONTENT,
    PARTNER_REWARD,
    PARTICIPATED_IN,
    PERSONA_STATE,
    POLL,
    POST,
    PREDICTED,
    PREDICTION_DISCUSSION,
    PRIVATE_LEAGUE,
    PURCHASED,
    QUESTION,
    QUIZ,
    QUIZ_QUESTION,
    RATING_SNAPSHOT,
    RECEIVED_NOTIFICATION,
    REDEEMED,
    SERVING_ONLY,
    SENTIMENT,
    SUBSCRIPTION_PRODUCT,
    SUBSCRIBED_TO,
    SUPER6_ROUND,
    TAG,
    TEAM,
    TOOL_CALL,
    TOPIC,
    USER,
    VOUCHER,
)
from app.core.exceptions import SourceInventoryError
from app.core.logging import get_logger

if TYPE_CHECKING:
    from app.db.source_inventory import SourceInventoryRepository

logger = get_logger(__name__)


# Source entry dataclass

@dataclass(frozen=True)
class SourceEntry:
    """
    Metadata record for a single warehouse source table.

    Attributes:
        source_name: Canonical warehouse table name.
        domain: Logical domain grouping.
        inclusion_mode: One of GRAPH_CORE, GRAPH_ENRICHMENT, SERVING_ONLY,
            FEATURE_SOURCE, or EXCLUDED.
        primary_keys: Columns that form the stable entity key. For composite
            keys, order matters and must be consistent across the codebase.
        freshness_field: Column used for incremental watermarking. None for
            static dimensions or tables that always use full refresh.
        graph_entity_mappings: Node labels or relationship type constants this
            table feeds. Empty for SERVING_ONLY, FEATURE_SOURCE, and EXCLUDED.
        notes: Brief rationale explaining the inclusion decision.
    """

    source_name: str
    domain: str
    inclusion_mode: str
    primary_keys: tuple[str, ...]
    freshness_field: str | None
    graph_entity_mappings: tuple[str, ...]
    notes: str = ""


# Registry definition

_REGISTRY: dict[str, SourceEntry] = {

    # Domain: identity

    "dim_users": SourceEntry(
        source_name="dim_users",
        domain="identity",
        inclusion_mode=GRAPH_CORE,
        primary_keys=("user_id",),
        freshness_field="last_activity_at_utc",
        graph_entity_mappings=(USER,),
        notes=(
            "Primary identity node. All User-related edges originate here. "
            "Incremental on last_activity_at_utc."
        ),
    ),

    "dim_avatars": SourceEntry(
        source_name="dim_avatars",
        domain="identity",
        inclusion_mode=GRAPH_CORE,
        primary_keys=("avatar_id",),
        freshness_field=None,
        graph_entity_mappings=(AVATAR,),
        notes=(
            "Static avatar catalog. No timestamp column; full refresh on each run."
        ),
    ),

    "dim_badges": SourceEntry(
        source_name="dim_badges",
        domain="identity",
        inclusion_mode=GRAPH_CORE,
        primary_keys=("badge_id",),
        freshness_field=None,
        graph_entity_mappings=(BADGE,),
        notes=(
            "Static badge catalog. No timestamp column; full refresh on each run."
        ),
    ),

    "app_users": SourceEntry(
        source_name="app_users",
        domain="identity",
        inclusion_mode=GRAPH_ENRICHMENT,
        primary_keys=("id",),
        freshness_field="updated_at",
        graph_entity_mappings=(USER,),
        notes=(
            "Auth bridge table. Enriches User nodes with login provider and "
            "credential metadata. Password field must be dropped by transformer "
            "before any downstream processing."
        ),
    ),

    # Domain: sports_core

    "dim_teams": SourceEntry(
        source_name="dim_teams",
        domain="sports_core",
        inclusion_mode=GRAPH_CORE,
        primary_keys=("team_id",),
        freshness_field=None,
        graph_entity_mappings=(TEAM,),
        notes=(
            "Core team dimension. No timestamp column; full refresh on each run."
        ),
    ),

    "dim_teams_enhanced": SourceEntry(
        source_name="dim_teams_enhanced",
        domain="sports_core",
        inclusion_mode=GRAPH_ENRICHMENT,
        primary_keys=("team_id",),
        freshness_field="last_fan_joined_at",
        graph_entity_mappings=(TEAM,),
        notes=(
            "Adds fan analytics computed properties to existing Team nodes. "
            "Not a separate node type. FK to dim_leagues must be resolved "
            "by transformer before graph write."
        ),
    ),

    "dim_leagues": SourceEntry(
        source_name="dim_leagues",
        domain="sports_core",
        inclusion_mode=GRAPH_CORE,
        primary_keys=("league_id",),
        freshness_field="updated_at",
        graph_entity_mappings=(LEAGUE,),
        notes="Core league dimension. Incremental on updated_at.",
    ),

    "dim_fixtures": SourceEntry(
        source_name="dim_fixtures",
        domain="sports_core",
        inclusion_mode=GRAPH_CORE,
        primary_keys=("fixture_id",),
        freshness_field="kickoff_at_utc",
        graph_entity_mappings=(MATCH,),
        notes=(
            "Core match/fixture dimension. Incremental on kickoff_at_utc. "
            "Carries home_team_id, away_team_id, and league_id FK references."
        ),
    ),

    # Domain: social

    "dim_private_leagues": SourceEntry(
        source_name="dim_private_leagues",
        domain="social",
        inclusion_mode=GRAPH_CORE,
        primary_keys=("private_league_id",),
        freshness_field=None,
        graph_entity_mappings=(PRIVATE_LEAGUE,),
        notes=(
            "Private league dimension. No timestamp column; full refresh or "
            "numeric watermark on private_league_id."
        ),
    ),

    "dim_private_league_members": SourceEntry(
        source_name="dim_private_league_members",
        domain="social",
        inclusion_mode=GRAPH_CORE,
        primary_keys=("membership_id",),
        freshness_field="joined_at",
        graph_entity_mappings=(MEMBER_OF,),
        notes=(
            "Membership junction table. Feeds MEMBER_OF relationship "
            "(User → PrivateLeague). membership_id may be null; fall back to "
            "composite (private_league_id, user_id) for deduplication."
        ),
    ),

    "dim_private_league_themes": SourceEntry(
        source_name="dim_private_league_themes",
        domain="social",
        inclusion_mode=GRAPH_ENRICHMENT,
        primary_keys=("theme_id",),
        freshness_field=None,
        graph_entity_mappings=(LEAGUE_THEME,),
        notes=(
            "Visual theme data for private leagues. No declared PK in DWH; "
            "theme_id has no unique constraint. Use private_league_id as "
            "de facto stable key. Static; full refresh."
        ),
    ),

    "dim_posts": SourceEntry(
        source_name="dim_posts",
        domain="social",
        inclusion_mode=GRAPH_CORE,
        primary_keys=("post_id",),
        freshness_field="published_at_utc",
        graph_entity_mappings=(POST,),
        notes="User-authored posts. Incremental on published_at_utc.",
    ),

    "dim_comments": SourceEntry(
        source_name="dim_comments",
        domain="social",
        inclusion_mode=GRAPH_CORE,
        primary_keys=("comment_id",),
        freshness_field="created_at_utc",
        graph_entity_mappings=(COMMENT,),
        notes=(
            "Comments on posts. Includes parent_comment_id for thread nesting. "
            "Incremental on created_at_utc."
        ),
    ),

    "dim_discussions": SourceEntry(
        source_name="dim_discussions",
        domain="social",
        inclusion_mode=GRAPH_CORE,
        primary_keys=("discussion_id",),
        freshness_field="created_at_utc",
        graph_entity_mappings=(DISCUSSION,),
        notes="Fixture-linked discussion threads. Incremental on created_at_utc.",
    ),

    "dim_prediction_discussions": SourceEntry(
        source_name="dim_prediction_discussions",
        domain="social",
        inclusion_mode=GRAPH_CORE,
        primary_keys=("prediction_discussion_id",),
        freshness_field="created_at_utc",
        graph_entity_mappings=(PREDICTION_DISCUSSION,),
        notes="Prediction-specific discussion threads. Incremental on created_at_utc.",
    ),

    "fct_discussion_events": SourceEntry(
        source_name="fct_discussion_events",
        domain="social",
        inclusion_mode=GRAPH_CORE,
        primary_keys=("event_id",),
        freshness_field="event_at_utc",
        graph_entity_mappings=(JOINED_DISCUSSION,),
        notes=(
            "User participation events within discussions. Feeds JOINED_DISCUSSION "
            "relationship (User → Discussion). Incremental on event_at_utc."
        ),
    ),

    "dim_chat_conversations_mysql": SourceEntry(
        source_name="dim_chat_conversations_mysql",
        domain="social",
        inclusion_mode=GRAPH_CORE,
        primary_keys=("conversation_id",),
        freshness_field="last_message_at",
        graph_entity_mappings=(CONVERSATION,),
        notes="Group and direct chat conversation dimension. Incremental on last_message_at.",
    ),

    "dim_chat_direct_pairs": SourceEntry(
        source_name="dim_chat_direct_pairs",
        domain="social",
        inclusion_mode=GRAPH_CORE,
        primary_keys=("direct_pair_key",),
        freshness_field="last_message_at",
        graph_entity_mappings=(DIRECT_PAIR,),
        notes=(
            "User-to-user direct message pair aggregates. direct_pair_key is a "
            "normalized composite user-user key already stable in the DWH. "
            "Incremental on last_message_at."
        ),
    ),

    # Domain: intelligence

    "fct_user_behavior": SourceEntry(
        source_name="fct_user_behavior",
        domain="intelligence",
        inclusion_mode=GRAPH_ENRICHMENT,
        primary_keys=("id",),
        freshness_field="last_calculated_at",
        graph_entity_mappings=(PERSONA_STATE,),
        notes=(
            "PCM stage and behaviour label per user. Enrichment input to "
            "PersonaState; not the canonical PersonaState node itself. "
            "Incremental on last_calculated_at."
        ),
    ),

    "fct_topics": SourceEntry(
        source_name="fct_topics",
        domain="intelligence",
        inclusion_mode=GRAPH_CORE,
        primary_keys=("id",),
        freshness_field="processed_at",
        graph_entity_mappings=(TOPIC,),
        notes=(
            "ML-derived topic labels per content item and user. "
            "Incremental on processed_at."
        ),
    ),

    "fct_sentiment": SourceEntry(
        source_name="fct_sentiment",
        domain="intelligence",
        inclusion_mode=GRAPH_CORE,
        primary_keys=("source_type", "item_id", "user_id"),
        freshness_field="processed_at",
        graph_entity_mappings=(SENTIMENT,),
        notes=(
            "ML-derived sentiment scores per content item and user. "
            "No declared PK in DWH; composite (source_type, item_id, user_id) "
            "is the stable key. Use stable_hash_key() to generate a synthetic "
            "node ID. Incremental on processed_at."
        ),
    ),

    "fct_team_affinity": SourceEntry(
        source_name="fct_team_affinity",
        domain="intelligence",
        inclusion_mode=GRAPH_CORE,
        primary_keys=("affinity_id",),
        freshness_field="calculated_at_utc",
        graph_entity_mappings=(HAS_AFFINITY,),
        notes=(
            "Computed user-to-team affinity scores. Feeds HAS_AFFINITY "
            "relationship (User → Team) with engagement and prediction accuracy "
            "properties. Incremental on calculated_at_utc."
        ),
    ),

    "fct_user_activities": SourceEntry(
        source_name="fct_user_activities",
        domain="intelligence",
        inclusion_mode=GRAPH_ENRICHMENT,
        primary_keys=("activity_id",),
        freshness_field="activity_at_utc",
        graph_entity_mappings=(USER,),
        notes=(
            "Fine-grained user activity events. Enrichment signal used in "
            "activity weight computation on User nodes. "
            "Incremental on activity_at_utc."
        ),
    ),

    "fct_user_sessions": SourceEntry(
        source_name="fct_user_sessions",
        domain="intelligence",
        inclusion_mode=FEATURE_SOURCE,
        primary_keys=("session_id",),
        freshness_field="session_start_utc",
        graph_entity_mappings=(),
        notes=(
            "Session aggregates. Too granular and aggregate for graph node "
            "representation. Feeds ML feature computation pipelines only. "
            "No graph entity mapping."
        ),
    ),

    "fct_user_rating_history": SourceEntry(
        source_name="fct_user_rating_history",
        domain="intelligence",
        inclusion_mode=GRAPH_CORE,
        primary_keys=("rating_event_id",),
        freshness_field="created_at_utc",
        graph_entity_mappings=(RATING_SNAPSHOT,),
        notes=(
            "Duel rating change events per user. No declared PK in DWH; "
            "rating_event_id treated as stable unique key. "
            "Incremental on created_at_utc."
        ),
    ),

    # Domain: competition

    "fct_predictions": SourceEntry(
        source_name="fct_predictions",
        domain="competition",
        inclusion_mode=GRAPH_CORE,
        primary_keys=("unified_prediction_id",),
        freshness_field="predicted_at_utc",
        graph_entity_mappings=(PREDICTED,),
        notes=(
            "Unified prediction fact table covering public and private league "
            "predictions. Feeds PREDICTED relationship (User → Match). "
            "Incremental on predicted_at_utc."
        ),
    ),

    "fct_prediction_duels": SourceEntry(
        source_name="fct_prediction_duels",
        domain="competition",
        inclusion_mode=GRAPH_CORE,
        primary_keys=("duel_id",),
        freshness_field="created_at_utc",
        graph_entity_mappings=(DUEL,),
        notes="Head-to-head prediction duel events. Incremental on created_at_utc.",
    ),

    "dim_super6_rounds": SourceEntry(
        source_name="dim_super6_rounds",
        domain="competition",
        inclusion_mode=GRAPH_CORE,
        primary_keys=("super6_round_id",),
        freshness_field="start_date_utc",
        graph_entity_mappings=(SUPER6_ROUND,),
        notes="Super6 round dimension. Incremental on start_date_utc.",
    ),

    "dim_super6_round_fixtures": SourceEntry(
        source_name="dim_super6_round_fixtures",
        domain="competition",
        inclusion_mode=GRAPH_CORE,
        primary_keys=("super6_round_fixture_id",),
        freshness_field=None,
        graph_entity_mappings=(HAS_FIXTURE,),
        notes=(
            "Junction table linking Super6 rounds to fixtures. "
            "Feeds HAS_FIXTURE relationship (Super6Round → Match). "
            "Static; full refresh."
        ),
    ),

    "fct_super6_participants": SourceEntry(
        source_name="fct_super6_participants",
        domain="competition",
        inclusion_mode=GRAPH_CORE,
        primary_keys=("super6_participant_id",),
        freshness_field="joined_at_utc",
        graph_entity_mappings=(PARTICIPATED_IN,),
        notes=(
            "User participation in Super6 rounds. Feeds PARTICIPATED_IN "
            "relationship (User → Super6Round). Incremental on joined_at_utc."
        ),
    ),

    "dim_lms_competitions": SourceEntry(
        source_name="dim_lms_competitions",
        domain="competition",
        inclusion_mode=GRAPH_CORE,
        primary_keys=("lms_competition_id",),
        freshness_field="created_at",
        graph_entity_mappings=(LMS_COMPETITION,),
        notes=(
            "Last Man Standing competition dimension. No declared PK in DWH; "
            "lms_competition_id treated as stable key. Incremental on created_at."
        ),
    ),

    # Domain: ai_communication

    "dim_chatbot_conversations": SourceEntry(
        source_name="dim_chatbot_conversations",
        domain="ai_communication",
        inclusion_mode=GRAPH_CORE,
        primary_keys=("conversation_id",),
        freshness_field="conversation_start_utc",
        graph_entity_mappings=(CHATBOT_CONVERSATION,),
        notes="AI chatbot conversation dimension. Incremental on conversation_start_utc.",
    ),

    "fct_chatbot_messages": SourceEntry(
        source_name="fct_chatbot_messages",
        domain="ai_communication",
        inclusion_mode=GRAPH_CORE,
        primary_keys=("message_id",),
        freshness_field="message_at_utc",
        graph_entity_mappings=(CHATBOT_MESSAGE,),
        notes=(
            "Individual chatbot message events. FK to dim_chatbot_conversations. "
            "Incremental on message_at_utc."
        ),
    ),

    "fct_chatbot_tool_calls": SourceEntry(
        source_name="fct_chatbot_tool_calls",
        domain="ai_communication",
        inclusion_mode=GRAPH_CORE,
        primary_keys=("tool_call_id",),
        freshness_field="tool_call_at_utc",
        graph_entity_mappings=(TOOL_CALL,),
        notes=(
            "Tool invocations within chatbot messages. FK to fct_chatbot_messages. "
            "Incremental on tool_call_at_utc."
        ),
    ),

    "dim_ai_articles": SourceEntry(
        source_name="dim_ai_articles",
        domain="ai_communication",
        inclusion_mode=GRAPH_CORE,
        primary_keys=("article_id",),
        freshness_field="updated_at_utc",
        graph_entity_mappings=(AI_ARTICLE,),
        notes=(
            "AI-generated article dimension. No declared PK in DWH; article_id "
            "treated as stable key. Incremental on updated_at_utc."
        ),
    ),

    "dim_news": SourceEntry(
        source_name="dim_news",
        domain="ai_communication",
        inclusion_mode=GRAPH_CORE,
        primary_keys=("news_id",),
        freshness_field="published_at_utc",
        graph_entity_mappings=(NEWS,),
        notes="Editorial news dimension. Incremental on published_at_utc.",
    ),

    # Domain: economy

    "fct_coin_transactions": SourceEntry(
        source_name="fct_coin_transactions",
        domain="economy",
        inclusion_mode=GRAPH_CORE,
        primary_keys=("event_id",),
        freshness_field="event_at_utc",
        graph_entity_mappings=(COIN_TRANSACTION,),
        notes="Coin earn/spend event log. Incremental on event_at_utc.",
    ),

    "dim_voucher_catalog": SourceEntry(
        source_name="dim_voucher_catalog",
        domain="economy",
        inclusion_mode=GRAPH_CORE,
        primary_keys=("voucher_key",),
        freshness_field="created_at",
        graph_entity_mappings=(VOUCHER,),
        notes=(
            "Voucher catalog dimension. No declared PK in DWH; voucher_key "
            "treated as stable key. Incremental on created_at."
        ),
    ),

    "fct_voucher_purchases": SourceEntry(
        source_name="fct_voucher_purchases",
        domain="economy",
        inclusion_mode=GRAPH_CORE,
        primary_keys=("purchase_id",),
        freshness_field="purchase_date_utc",
        graph_entity_mappings=(PURCHASED,),
        notes=(
            "Voucher purchase events. Feeds PURCHASED relationship "
            "(User → Voucher). No declared PK in DWH; purchase_id treated as "
            "stable key. Incremental on purchase_date_utc."
        ),
    ),

    "dim_partner_reward_catalog": SourceEntry(
        source_name="dim_partner_reward_catalog",
        domain="economy",
        inclusion_mode=GRAPH_CORE,
        primary_keys=("reward_key",),
        freshness_field="created_at",
        graph_entity_mappings=(PARTNER_REWARD,),
        notes=(
            "Partner reward catalog dimension. No declared PK in DWH; reward_key "
            "treated as stable key. Incremental on created_at."
        ),
    ),

    "fct_partner_reward_inventory": SourceEntry(
        source_name="fct_partner_reward_inventory",
        domain="economy",
        inclusion_mode=GRAPH_ENRICHMENT,
        primary_keys=("inventory_event_id",),
        freshness_field="created_at_utc",
        graph_entity_mappings=(PARTNER_REWARD,),
        notes=(
            "Partner reward stock and event enrichment. Adds stock and event "
            "detail to existing PartnerReward nodes. No declared PK in DWH; "
            "inventory_event_id treated as stable key. Incremental on created_at_utc."
        ),
    ),

    "fct_partner_reward_redemptions": SourceEntry(
        source_name="fct_partner_reward_redemptions",
        domain="economy",
        inclusion_mode=GRAPH_CORE,
        primary_keys=("redemption_id",),
        freshness_field="redeemed_at_utc",
        graph_entity_mappings=(REDEEMED,),
        notes=(
            "Partner reward redemption events. Feeds REDEEMED relationship "
            "(User → PartnerReward). user_email field must be dropped or hashed "
            "by transformer — never written to graph. Incremental on redeemed_at_utc."
        ),
    ),

    "dim_subscription_products": SourceEntry(
        source_name="dim_subscription_products",
        domain="economy",
        inclusion_mode=GRAPH_CORE,
        primary_keys=("subscription_type_id",),
        freshness_field=None,
        graph_entity_mappings=(SUBSCRIPTION_PRODUCT,),
        notes=(
            "Subscription product catalog. Static dimension; "
            "full refresh on each run."
        ),
    ),

    "fct_subscription_lifecycle": SourceEntry(
        source_name="fct_subscription_lifecycle",
        domain="economy",
        inclusion_mode=GRAPH_CORE,
        primary_keys=("lifecycle_event_id",),
        freshness_field="event_timestamp_utc",
        graph_entity_mappings=(SUBSCRIBED_TO,),
        notes=(
            "Subscription lifecycle events (new, renewal, churn, win-back). "
            "Feeds SUBSCRIBED_TO relationship (User → SubscriptionProduct). "
            "No declared PK in DWH; lifecycle_event_id treated as stable key. "
            "Incremental on event_timestamp_utc."
        ),
    ),

    "fct_financials": SourceEntry(
        source_name="fct_financials",
        domain="economy",
        inclusion_mode=GRAPH_CORE,
        primary_keys=("event_id",),
        freshness_field="event_at_utc",
        graph_entity_mappings=(FINANCIAL_EVENT,),
        notes="Payment and financial event log. Incremental on event_at_utc.",
    ),

    "fct_awards_and_achievements": SourceEntry(
        source_name="fct_awards_and_achievements",
        domain="economy",
        inclusion_mode=GRAPH_CORE,
        primary_keys=("award_id",),
        freshness_field="earned_at_utc",
        graph_entity_mappings=(ACHIEVEMENT, ACHIEVED),
        notes=(
            "Achievement and award events. Feeds both Achievement node creation "
            "and ACHIEVED relationship (User → Achievement). "
            "Incremental on earned_at_utc."
        ),
    ),

    # Domain: engagement

    "dim_fixture_polls_enhanced": SourceEntry(
        source_name="dim_fixture_polls_enhanced",
        domain="engagement",
        inclusion_mode=GRAPH_CORE,
        primary_keys=("fixture_poll_id",),
        freshness_field="created_at_utc",
        graph_entity_mappings=(POLL,),
        notes=(
            "Fixture-linked poll dimension with engagement analytics. "
            "Incremental on created_at_utc."
        ),
    ),

    "dim_questions": SourceEntry(
        source_name="dim_questions",
        domain="engagement",
        inclusion_mode=GRAPH_CORE,
        primary_keys=("question_id",),
        freshness_field="created_at_utc",
        graph_entity_mappings=(QUESTION,),
        notes="Core question catalog. Incremental on created_at_utc.",
    ),

    "dim_questions_enhanced": SourceEntry(
        source_name="dim_questions_enhanced",
        domain="engagement",
        inclusion_mode=GRAPH_ENRICHMENT,
        primary_keys=("question_id",),
        freshness_field="last_response_at_utc",
        graph_entity_mappings=(QUESTION,),
        notes=(
            "Adds engagement analytics to existing Question nodes. "
            "Shares question_id PK with dim_questions. "
            "Incremental on last_response_at_utc."
        ),
    ),

    "dim_quizzes": SourceEntry(
        source_name="dim_quizzes",
        domain="engagement",
        inclusion_mode=GRAPH_CORE,
        primary_keys=("quiz_id",),
        freshness_field="created_at_utc",
        graph_entity_mappings=(QUIZ,),
        notes="Quiz catalog. Incremental on created_at_utc.",
    ),

    "dim_quiz_questions_enhanced": SourceEntry(
        source_name="dim_quiz_questions_enhanced",
        domain="engagement",
        inclusion_mode=GRAPH_CORE,
        primary_keys=("quiz_question_id",),
        freshness_field="created_at_utc",
        graph_entity_mappings=(QUIZ_QUESTION,),
        notes=(
            "Quiz question catalog with engagement analytics. "
            "Incremental on created_at_utc."
        ),
    ),

    "dim_tags": SourceEntry(
        source_name="dim_tags",
        domain="engagement",
        inclusion_mode=GRAPH_CORE,
        primary_keys=("tag_id",),
        freshness_field="last_used_at_utc",
        graph_entity_mappings=(TAG,),
        notes=(
            "Tag catalog with trending signals. Carries team_id and league_id "
            "references. Incremental on last_used_at_utc."
        ),
    ),

    "dim_notification_content": SourceEntry(
        source_name="dim_notification_content",
        domain="engagement",
        inclusion_mode=GRAPH_CORE,
        primary_keys=("content_id",),
        freshness_field="last_seen_at_utc",
        graph_entity_mappings=(NOTIFICATION_CONTENT,),
        notes=(
            "Normalized notification message catalog. No declared PK in DWH; "
            "content_id treated as stable key. Incremental on last_seen_at_utc."
        ),
    ),

    "dim_notification_preferences": SourceEntry(
        source_name="dim_notification_preferences",
        domain="engagement",
        inclusion_mode=GRAPH_ENRICHMENT,
        primary_keys=("user_id",),
        freshness_field="preference_updated_at_utc",
        graph_entity_mappings=(USER,),
        notes=(
            "Notification consent and device registration per user. "
            "One row per (user_id, subscription_category) pair; transformer "
            "must group by user_id before writing enrichment properties to "
            "User nodes. Incremental on preference_updated_at_utc."
        ),
    ),

    "fct_notification_content_daily": SourceEntry(
        source_name="fct_notification_content_daily",
        domain="engagement",
        inclusion_mode=FEATURE_SOURCE,
        primary_keys=("content_day_id",),
        freshness_field="first_sent_at_utc",
        graph_entity_mappings=(),
        notes=(
            "Daily delivery aggregates per notification content item. "
            "Feeds notification scoring models. No graph entity mapping."
        ),
    ),

    "jct_notification_recipients": SourceEntry(
        source_name="jct_notification_recipients",
        domain="engagement",
        inclusion_mode=GRAPH_CORE,
        primary_keys=("notification_id", "user_id"),
        freshness_field="sent_at_utc",
        graph_entity_mappings=(RECEIVED_NOTIFICATION,),
        notes=(
            "Junction table linking notifications to recipient users. "
            "Feeds RECEIVED_NOTIFICATION relationship (User → NotificationContent). "
            "No declared PK in DWH; composite (notification_id, user_id) is the "
            "stable key. Incremental on sent_at_utc."
        ),
    ),

    "fct_user_notification_stats": SourceEntry(
        source_name="fct_user_notification_stats",
        domain="engagement",
        inclusion_mode=FEATURE_SOURCE,
        primary_keys=("user_id",),
        freshness_field="last_notification_at_utc",
        graph_entity_mappings=(),
        notes=(
            "Per-user notification engagement aggregates. Feeds notification "
            "scoring and serving layer. No graph entity mapping."
        ),
    ),

    # Domain: ops

    "fct_moderation_events": SourceEntry(
        source_name="fct_moderation_events",
        domain="ops",
        inclusion_mode=GRAPH_CORE,
        primary_keys=("event_id",),
        freshness_field="event_at_utc",
        graph_entity_mappings=(MODERATION_EVENT,),
        notes="Moderation action event log. Incremental on event_at_utc.",
    ),

    "fct_daily_metrics": SourceEntry(
        source_name="fct_daily_metrics",
        domain="ops",
        inclusion_mode=SERVING_ONLY,
        primary_keys=("metric_date",),
        freshness_field="metric_date",
        graph_entity_mappings=(),
        notes=(
            "Platform-level aggregate KPIs. Not entity-level; no graph node "
            "representation. Consumed by operational dashboards only."
        ),
    ),

    "fct_content_engagement_daily": SourceEntry(
        source_name="fct_content_engagement_daily",
        domain="ops",
        inclusion_mode=SERVING_ONLY,
        primary_keys=("engagement_id",),
        freshness_field="metric_date",
        graph_entity_mappings=(),
        notes=(
            "Daily content engagement rollup. Feeds dashboards, not graph. "
            "No declared PK in DWH."
        ),
    ),

    "fct_heatmap_events": SourceEntry(
        source_name="fct_heatmap_events",
        domain="ops",
        inclusion_mode=FEATURE_SOURCE,
        primary_keys=("heatmap_event_id",),
        freshness_field="event_timestamp_utc",
        graph_entity_mappings=(),
        notes=(
            "Raw UX click/scroll event stream. Too granular for graph. "
            "Feeds behaviour model feature computation. No declared PK in DWH."
        ),
    ),

    "fct_retention_cohorts": SourceEntry(
        source_name="fct_retention_cohorts",
        domain="ops",
        inclusion_mode=SERVING_ONLY,
        primary_keys=("cohort_date_key", "period_weeks_since_cohort"),
        freshness_field="cohort_date",
        graph_entity_mappings=(),
        notes=(
            "Cohort retention analytics. No per-user entity mapping; "
            "feeds cohort dashboards only."
        ),
    ),

    "fct_team_daily_growth": SourceEntry(
        source_name="fct_team_daily_growth",
        domain="ops",
        inclusion_mode=FEATURE_SOURCE,
        primary_keys=("metric_date", "team_id"),
        freshness_field="metric_date",
        graph_entity_mappings=(),
        notes=(
            "Team-level fan growth time series. Feeds team analytics model "
            "features. No graph entity mapping."
        ),
    ),

    "dim_influencer_leagues": SourceEntry(
        source_name="dim_influencer_leagues",
        domain="ops",
        inclusion_mode=GRAPH_CORE,
        primary_keys=("influencer_league_id",),
        freshness_field="updated_at",
        graph_entity_mappings=(INFLUENCER_LEAGUE,),
        notes="Influencer league dimension. Incremental on updated_at.",
    ),

    # Domain: excluded

    "__drizzle_migrations": SourceEntry(
        source_name="__drizzle_migrations",
        domain="excluded",
        inclusion_mode=EXCLUDED,
        primary_keys=("id",),
        freshness_field=None,
        graph_entity_mappings=(),
        notes=(
            "Internal Drizzle ORM migration tracking table. "
            "No analytical or graph value."
        ),
    ),
}



# Registry access helpers


def get_all_sources() -> list[SourceEntry]:
    """
    Return all registered source entries.
    """
    return list(_REGISTRY.values())


def get_source(source_name: str) -> SourceEntry | None:
    """
    Return the registry entry for a specific source name, or None if not found.
    """
    return _REGISTRY.get(source_name)


def require_source(source_name: str) -> SourceEntry:
    """
    Return the registry entry for a specific source name.

    Raises:
        SourceInventoryError: If the source is not registered.
    """
    entry = _REGISTRY.get(source_name)
    if entry is None:
        raise SourceInventoryError(
            "Source not found in registry",
            source_name=source_name,
        )
    return entry


def list_by_inclusion_mode(mode: str) -> list[SourceEntry]:
    """
    Return all sources with the given inclusion mode.
    """
    return [entry for entry in _REGISTRY.values() if entry.inclusion_mode == mode]


def list_graph_core() -> list[SourceEntry]:
    """Return all GRAPH_CORE sources."""
    return list_by_inclusion_mode(GRAPH_CORE)


def list_enrichment() -> list[SourceEntry]:
    """Return all GRAPH_ENRICHMENT sources."""
    return list_by_inclusion_mode(GRAPH_ENRICHMENT)


def list_serving_only() -> list[SourceEntry]:
    """Return all SERVING_ONLY sources."""
    return list_by_inclusion_mode(SERVING_ONLY)


def list_feature_sources() -> list[SourceEntry]:
    """Return all FEATURE_SOURCE sources."""
    return list_by_inclusion_mode(FEATURE_SOURCE)


def list_excluded() -> list[SourceEntry]:
    """Return all EXCLUDED sources."""
    return list_by_inclusion_mode(EXCLUDED)


def list_by_domain(domain: str) -> list[SourceEntry]:
    """
    Return all sources belonging to the given domain.
    """
    return [entry for entry in _REGISTRY.values() if entry.domain == domain]


def get_all_domains() -> list[str]:
    """
    Return a sorted, deduplicated list of all domains in the registry.
    """
    return sorted({entry.domain for entry in _REGISTRY.values()})


def get_all_source_names() -> set[str]:
    """
    Return the set of all registered source names.
    """
    return set(_REGISTRY.keys())


# Persistence sync helper


def sync_registry_to_db(repo: SourceInventoryRepository) -> None:
    """
    Upsert every registry entry into the metadata DB source inventory table.

    This is the only function in this module with external side effects.
    It is safe to import this module without calling this function.

    Callers:
        scripts/run_source_inventory_audit.py

    Args:
        repo: SourceInventoryRepository from app.db.source_inventory.

    Raises:
        SourceInventoryError: If any upsert fails after the internal
            MetadataDatabaseError is raised by the repository.
    """
    entries = get_all_sources()
    succeeded = 0
    failed = 0

    for entry in entries:
        try:
            repo.upsert_source(
                source_name=entry.source_name,
                domain=entry.domain,
                inclusion_mode=entry.inclusion_mode,
                freshness_field=entry.freshness_field,
                key_fields=list(entry.primary_keys),
                graph_entity_mappings=list(entry.graph_entity_mappings),
                notes=entry.notes,
            )
            succeeded += 1
        except Exception as exc:  # noqa: BLE001
            failed += 1
            logger.error(
                "Failed to sync source registry entry to DB",
                extra={
                    "source_name": entry.source_name,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                },
            )

    logger.info(
        "Source registry sync completed",
        extra={
            "total": len(entries),
            "succeeded": succeeded,
            "failed": failed,
        },
    )

    if failed > 0:
        raise SourceInventoryError(
            "Source registry sync completed with failures",
            total=len(entries),
            succeeded=succeeded,
            failed=failed,
        )