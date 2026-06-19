"""
Neo4j constraint and index definitions for Project Pulse Knowledge Graph.

This file is the source of truth for the constraints pipeline. Every
uniqueness constraint and lookup index that must exist before data loading
is defined here as a typed object.

Design rules:
- All constraint names follow the pattern: unique_{label_lower}_{property}
- All index names follow the pattern: idx_{label_lower}_{property}
- Names must be stable across pipeline runs (Neo4j uses them as identifiers).
- build_constraint_cypher() and build_index_cypher() produce Neo4j 5.x
  syntax using CREATE CONSTRAINT / CREATE INDEX IF NOT EXISTS.
- The constraints pipeline must call get_all_constraints() then
  get_all_indexes() and apply them in that order.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.constants import (
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
    FINANCIAL_EVENT,
    INFLUENCER_LEAGUE,
    LEAGUE,
    LEAGUE_THEME,
    LMS_COMPETITION,
    MATCH,
    MODERATION_EVENT,
    NEWS,
    NOTIFICATION_CONTENT,
    PARTNER_REWARD,
    PERSONA_STATE,
    POLL,
    POST,
    PREDICTION_DISCUSSION,
    PRIVATE_LEAGUE,
    QUESTION,
    QUIZ,
    QUIZ_QUESTION,
    RATING_SNAPSHOT,
    SENTIMENT,
    SUBSCRIPTION_PRODUCT,
    SUPER6_ROUND,
    TAG,
    TEAM,
    TOOL,
    TOOL_CALL,
    TOPIC,
    USER,
    VOUCHER,
)


# Structured constraint and index objects


@dataclass(frozen=True)
class GraphConstraint:
    """
    Structured representation of a Neo4j constraint.

    Attributes:
        label: The node label this constraint applies to.
        property: The property field constrained.
        constraint_type: "UNIQUE" or "EXISTS".
        name: Stable Neo4j constraint name used in CREATE CONSTRAINT statements.
    """

    label: str
    property: str
    constraint_type: str  # "UNIQUE" | "EXISTS"
    name: str


@dataclass(frozen=True)
class GraphIndex:
    """
    Structured representation of a Neo4j index.

    Attributes:
        label: The node label this index applies to.
        property: The property field indexed.
        index_type: "RANGE" (default for Neo4j 5.x) or "TEXT" for full-text.
        name: Stable Neo4j index name used in CREATE INDEX statements.
    """

    label: str
    property: str
    index_type: str  # "RANGE" | "TEXT"
    name: str


# Uniqueness constraints — one per node label

_UNIQUENESS_CONSTRAINTS: list[GraphConstraint] = [
    GraphConstraint(label=USER,                  property="id", constraint_type="UNIQUE", name="unique_user_id"),
    GraphConstraint(label=AVATAR,                property="id", constraint_type="UNIQUE", name="unique_avatar_id"),
    GraphConstraint(label=BADGE,                 property="id", constraint_type="UNIQUE", name="unique_badge_id"),
    GraphConstraint(label=TEAM,                  property="id", constraint_type="UNIQUE", name="unique_team_id"),
    GraphConstraint(label=LEAGUE,                property="id", constraint_type="UNIQUE", name="unique_league_id"),
    GraphConstraint(label=MATCH,                 property="id", constraint_type="UNIQUE", name="unique_match_id"),
    GraphConstraint(label=PRIVATE_LEAGUE,        property="id", constraint_type="UNIQUE", name="unique_private_league_id"),
    GraphConstraint(label=LEAGUE_THEME,          property="id", constraint_type="UNIQUE", name="unique_league_theme_id"),
    GraphConstraint(label=INFLUENCER_LEAGUE,     property="id", constraint_type="UNIQUE", name="unique_influencer_league_id"),
    GraphConstraint(label=POST,                  property="id", constraint_type="UNIQUE", name="unique_post_id"),
    GraphConstraint(label=COMMENT,               property="id", constraint_type="UNIQUE", name="unique_comment_id"),
    GraphConstraint(label=DISCUSSION,            property="id", constraint_type="UNIQUE", name="unique_discussion_id"),
    GraphConstraint(label=PREDICTION_DISCUSSION, property="id", constraint_type="UNIQUE", name="unique_prediction_discussion_id"),
    GraphConstraint(label=CONVERSATION,          property="id", constraint_type="UNIQUE", name="unique_conversation_id"),
    GraphConstraint(label=DIRECT_PAIR,           property="id", constraint_type="UNIQUE", name="unique_direct_pair_id"),
    GraphConstraint(label=PERSONA_STATE,         property="id", constraint_type="UNIQUE", name="unique_persona_state_id"),
    GraphConstraint(label=TOPIC,                 property="id", constraint_type="UNIQUE", name="unique_topic_id"),
    GraphConstraint(label=SENTIMENT,             property="id", constraint_type="UNIQUE", name="unique_sentiment_id"),
    GraphConstraint(label=RATING_SNAPSHOT,       property="id", constraint_type="UNIQUE", name="unique_rating_snapshot_id"),
    GraphConstraint(label=CHATBOT_CONVERSATION,  property="id", constraint_type="UNIQUE", name="unique_chatbot_conversation_id"),
    GraphConstraint(label=CHATBOT_MESSAGE,       property="id", constraint_type="UNIQUE", name="unique_chatbot_message_id"),
    GraphConstraint(label=TOOL_CALL,             property="id", constraint_type="UNIQUE", name="unique_tool_call_id"),
    GraphConstraint(label=TOOL,                  property="id", constraint_type="UNIQUE", name="unique_tool_id"),
    GraphConstraint(label=COIN_TRANSACTION,      property="id", constraint_type="UNIQUE", name="unique_coin_transaction_id"),
    GraphConstraint(label=VOUCHER,               property="id", constraint_type="UNIQUE", name="unique_voucher_id"),
    GraphConstraint(label=PARTNER_REWARD,        property="id", constraint_type="UNIQUE", name="unique_partner_reward_id"),
    GraphConstraint(label=SUBSCRIPTION_PRODUCT,  property="id", constraint_type="UNIQUE", name="unique_subscription_product_id"),
    GraphConstraint(label=ACHIEVEMENT,           property="id", constraint_type="UNIQUE", name="unique_achievement_id"),
    GraphConstraint(label=FINANCIAL_EVENT,       property="id", constraint_type="UNIQUE", name="unique_financial_event_id"),
    GraphConstraint(label=DUEL,                  property="id", constraint_type="UNIQUE", name="unique_duel_id"),
    GraphConstraint(label=SUPER6_ROUND,          property="id", constraint_type="UNIQUE", name="unique_super6_round_id"),
    GraphConstraint(label=LMS_COMPETITION,       property="id", constraint_type="UNIQUE", name="unique_lms_competition_id"),
    GraphConstraint(label=POLL,                  property="id", constraint_type="UNIQUE", name="unique_poll_id"),
    GraphConstraint(label=QUESTION,              property="id", constraint_type="UNIQUE", name="unique_question_id"),
    GraphConstraint(label=QUIZ,                  property="id", constraint_type="UNIQUE", name="unique_quiz_id"),
    GraphConstraint(label=QUIZ_QUESTION,         property="id", constraint_type="UNIQUE", name="unique_quiz_question_id"),
    GraphConstraint(label=TAG,                   property="id", constraint_type="UNIQUE", name="unique_tag_id"),
    GraphConstraint(label=NOTIFICATION_CONTENT,  property="id", constraint_type="UNIQUE", name="unique_notification_content_id"),
    GraphConstraint(label=MODERATION_EVENT,      property="id", constraint_type="UNIQUE", name="unique_moderation_event_id"),
    GraphConstraint(label=AI_ARTICLE,            property="id", constraint_type="UNIQUE", name="unique_ai_article_id"),
    GraphConstraint(label=NEWS,                  property="id", constraint_type="UNIQUE", name="unique_news_id"),
]


# Lookup indexes

_LOOKUP_INDEXES: list[GraphIndex] = [
    # User — high-cardinality filter axes for persona and tribe queries
    GraphIndex(label=USER,                 property="country",                   index_type="RANGE", name="idx_user_country"),
    GraphIndex(label=USER,                 property="gender",                    index_type="RANGE", name="idx_user_gender"),
    GraphIndex(label=USER,                 property="current_subscription_name", index_type="RANGE", name="idx_user_subscription"),
    GraphIndex(label=USER,                 property="is_suspended",              index_type="RANGE", name="idx_user_suspended"),

    # Match — temporal and status lookups for incremental extraction
    GraphIndex(label=MATCH,                property="kickoff_at",                index_type="RANGE", name="idx_match_kickoff_at"),
    GraphIndex(label=MATCH,                property="status",                    index_type="RANGE", name="idx_match_status"),

    # Content — temporal lookups for freshness and serving queries
    GraphIndex(label=POST,                 property="published_at",              index_type="RANGE", name="idx_post_published_at"),
    GraphIndex(label=COMMENT,              property="created_at",                index_type="RANGE", name="idx_comment_created_at"),

    # Intelligence — label lookups for topic and sentiment clustering
    GraphIndex(label=TOPIC,                property="topic_label",               index_type="RANGE", name="idx_topic_label"),
    GraphIndex(label=SENTIMENT,            property="sentiment_label",           index_type="RANGE", name="idx_sentiment_label"),

    # Persona — stage lookups for persona pipeline and inference
    GraphIndex(label=PERSONA_STATE,        property="pcm_stage",                 index_type="RANGE", name="idx_persona_state_pcm_stage"),

    # AI / communication
    GraphIndex(label=CHATBOT_CONVERSATION, property="conversation_start",        index_type="RANGE", name="idx_chatbot_conversation_start"),

    # Moderation
    GraphIndex(label=MODERATION_EVENT,     property="event_at",                  index_type="RANGE", name="idx_moderation_event_at"),

    # Tags — name and trending lookups for content recommendation
    GraphIndex(label=TAG,                  property="tag_name",                  index_type="RANGE", name="idx_tag_name"),
    GraphIndex(label=TAG,                  property="is_trending",               index_type="RANGE", name="idx_tag_trending"),
]


# Access helpers


def get_all_constraints() -> list[GraphConstraint]:
    """
    Return all registered graph constraints.

    The constraints pipeline should apply these before indexes and before
    any data is loaded.
    """
    return list(_UNIQUENESS_CONSTRAINTS)


def get_all_indexes() -> list[GraphIndex]:
    """
    Return all registered graph indexes.

    Apply these after constraints.
    """
    return list(_LOOKUP_INDEXES)


def build_constraint_cypher(constraint: GraphConstraint) -> str:
    """
    Build a Neo4j 5.x CREATE CONSTRAINT IF NOT EXISTS statement.

    Args:
        constraint: GraphConstraint instance.

    Returns:
        Cypher DDL string ready to execute against the Neo4j driver.

    Example output:
        CREATE CONSTRAINT unique_user_id IF NOT EXISTS
        FOR (n:User) REQUIRE n.id IS UNIQUE
    """
    if constraint.constraint_type == "UNIQUE":
        return (
            f"CREATE CONSTRAINT {constraint.name} IF NOT EXISTS\n"
            f"FOR (n:{constraint.label}) REQUIRE n.{constraint.property} IS UNIQUE"
        )

    if constraint.constraint_type == "EXISTS":
        return (
            f"CREATE CONSTRAINT {constraint.name} IF NOT EXISTS\n"
            f"FOR (n:{constraint.label}) REQUIRE n.{constraint.property} IS NOT NULL"
        )

    raise ValueError(
        f"Unsupported constraint_type: {constraint.constraint_type!r}. "
        "Expected 'UNIQUE' or 'EXISTS'."
    )


def build_index_cypher(index: GraphIndex) -> str:
    """
    Build a Neo4j 5.x CREATE INDEX IF NOT EXISTS statement.

    Args:
        index: GraphIndex instance.

    Returns:
        Cypher DDL string ready to execute against the Neo4j driver.

    Example output (RANGE):
        CREATE INDEX idx_user_country IF NOT EXISTS
        FOR (n:User) ON (n.country)

    Example output (TEXT):
        CREATE TEXT INDEX idx_tag_name IF NOT EXISTS
        FOR (n:Tag) ON (n.tag_name)
    """
    if index.index_type == "RANGE":
        return (
            f"CREATE INDEX {index.name} IF NOT EXISTS\n"
            f"FOR (n:{index.label}) ON (n.{index.property})"
        )

    if index.index_type == "TEXT":
        return (
            f"CREATE TEXT INDEX {index.name} IF NOT EXISTS\n"
            f"FOR (n:{index.label}) ON (n.{index.property})"
        )

    raise ValueError(
        f"Unsupported index_type: {index.index_type!r}. "
        "Expected 'RANGE' or 'TEXT'."
    )