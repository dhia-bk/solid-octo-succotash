"""
Stable merge key strategy declarations for graph artifacts.

This module defines how graph identity is derived for every node-producing,
relationship-producing, and enrichment-producing source.

It answers:

- which source field(s) define identity for a graph artifact
- when to use a direct source key
- when to use a composite key
- when to use fallback fields
- when to use a synthetic hash key

This is a critical part of graph correctness. Merge-key logic must be declared
here, not invented inside transformers or loaders.

Design rules:
- Every graph-producing or graph-enriching source must have a declared
  MergeKeySpec for each emitted artifact.
- The mapping layer owns merge-key strategy. Transformers consume this file;
  they do not define identity rules ad hoc.
- Validation in this module is structural and registry-aware. It verifies
  merge-key completeness and consistency against the warehouse schema layer
  when that schema can be introspected at runtime.
- Synthetic-key strategies must be justified in notes.
- Fallback strategies must declare fallback_fields.
- Direct and composite strategies must declare source_fields.

Primary outputs:
- MERGE_KEY_SPECS: full registry of merge-key declarations
- lookup helpers for merge-key access
- validation helpers for merge-key completeness and correctness

This module does NOT define:
- field/property mappings
- endpoint resolution
- property ownership
- actual key-building functions

Those belong to other mapping files or to runtime helpers in later stages.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.mappings.base import GraphArtifactKind

DIRECT_STRATEGY = "direct"
COMPOSITE_STRATEGY = "composite"
FALLBACK_STRATEGY = "fallback"
SYNTHETIC_HASH_STRATEGY = "synthetic_hash"

VALID_MERGE_KEY_STRATEGIES: frozenset[str] = frozenset(
    {
        DIRECT_STRATEGY,
        COMPOSITE_STRATEGY,
        FALLBACK_STRATEGY,
        SYNTHETIC_HASH_STRATEGY,
    }
)


@dataclass(frozen=True)
class MergeKeySpec:
    """
    Stable merge-key strategy declaration for one graph artifact.

    Attributes:
        source_name: Logical warehouse source/table name.
        artifact_kind: "node", "relationship", or "enrichment".
        target_name: Graph target label or relationship type.
        strategy: Identity strategy name.
        source_fields: Primary source fields used by the strategy.
        fallback_fields: Fallback source fields when strategy == "fallback".
        notes: Optional explanatory notes and required justification for
            synthetic strategies.
    """

    source_name: str
    artifact_kind: str
    target_name: str
    strategy: str
    source_fields: tuple[str, ...]
    fallback_fields: tuple[str, ...]
    notes: str | None


# Registry

MERGE_KEY_SPECS: tuple[MergeKeySpec, ...] = (
    
    # Core node sources
    
    MergeKeySpec(
        source_name="dim_users",
        artifact_kind=GraphArtifactKind.NODE.value,
        target_name="User",
        strategy=DIRECT_STRATEGY,
        source_fields=("user_id",),
        fallback_fields=(),
        notes="Primary user identity comes directly from user_id.",
    ),
    MergeKeySpec(
        source_name="dim_avatars",
        artifact_kind=GraphArtifactKind.NODE.value,
        target_name="Avatar",
        strategy=DIRECT_STRATEGY,
        source_fields=("avatar_id",),
        fallback_fields=(),
        notes="Avatar catalog identity is avatar_id.",
    ),
    MergeKeySpec(
        source_name="dim_badges",
        artifact_kind=GraphArtifactKind.NODE.value,
        target_name="Badge",
        strategy=DIRECT_STRATEGY,
        source_fields=("badge_id",),
        fallback_fields=(),
        notes="Badge catalog identity is badge_id.",
    ),
    MergeKeySpec(
        source_name="dim_teams",
        artifact_kind=GraphArtifactKind.NODE.value,
        target_name="Team",
        strategy=DIRECT_STRATEGY,
        source_fields=("team_id",),
        fallback_fields=(),
        notes="Canonical team identity comes from team_id.",
    ),
    MergeKeySpec(
        source_name="dim_leagues",
        artifact_kind=GraphArtifactKind.NODE.value,
        target_name="League",
        strategy=DIRECT_STRATEGY,
        source_fields=("league_id",),
        fallback_fields=(),
        notes="Canonical league identity comes from league_id.",
    ),
    MergeKeySpec(
        source_name="dim_fixtures",
        artifact_kind=GraphArtifactKind.NODE.value,
        target_name="Match",
        strategy=DIRECT_STRATEGY,
        source_fields=("fixture_id",),
        fallback_fields=(),
        notes="Canonical match identity comes from fixture_id.",
    ),
    MergeKeySpec(
        source_name="dim_private_leagues",
        artifact_kind=GraphArtifactKind.NODE.value,
        target_name="PrivateLeague",
        strategy=DIRECT_STRATEGY,
        source_fields=("private_league_id",),
        fallback_fields=(),
        notes="Private league identity is private_league_id.",
    ),
    MergeKeySpec(
        source_name="dim_posts",
        artifact_kind=GraphArtifactKind.NODE.value,
        target_name="Post",
        strategy=DIRECT_STRATEGY,
        source_fields=("post_id",),
        fallback_fields=(),
        notes="Post identity is post_id.",
    ),
    MergeKeySpec(
        source_name="dim_comments",
        artifact_kind=GraphArtifactKind.NODE.value,
        target_name="Comment",
        strategy=DIRECT_STRATEGY,
        source_fields=("comment_id",),
        fallback_fields=(),
        notes="Comment identity is comment_id.",
    ),
    MergeKeySpec(
        source_name="dim_discussions",
        artifact_kind=GraphArtifactKind.NODE.value,
        target_name="Discussion",
        strategy=DIRECT_STRATEGY,
        source_fields=("discussion_id",),
        fallback_fields=(),
        notes="Discussion identity is discussion_id.",
    ),
    MergeKeySpec(
        source_name="dim_prediction_discussions",
        artifact_kind=GraphArtifactKind.NODE.value,
        target_name="PredictionDiscussion",
        strategy=DIRECT_STRATEGY,
        source_fields=("prediction_discussion_id",),
        fallback_fields=(),
        notes="Prediction discussion identity is prediction_discussion_id.",
    ),
    MergeKeySpec(
        source_name="dim_chat_conversations_mysql",
        artifact_kind=GraphArtifactKind.NODE.value,
        target_name="Conversation",
        strategy=DIRECT_STRATEGY,
        source_fields=("conversation_id",),
        fallback_fields=(),
        notes="Conversation identity is conversation_id.",
    ),
    MergeKeySpec(
        source_name="dim_chat_direct_pairs",
        artifact_kind=GraphArtifactKind.NODE.value,
        target_name="DirectPair",
        strategy=DIRECT_STRATEGY,
        source_fields=("direct_pair_id",),
        fallback_fields=(),
        notes="Direct pair identity is direct_pair_id.",
    ),
    MergeKeySpec(
        source_name="dim_chatbot_conversations",
        artifact_kind=GraphArtifactKind.NODE.value,
        target_name="ChatbotConversation",
        strategy=DIRECT_STRATEGY,
        source_fields=("conversation_id",),
        fallback_fields=(),
        notes="Chatbot conversation identity is conversation_id.",
    ),
    MergeKeySpec(
        source_name="fct_chatbot_messages",
        artifact_kind=GraphArtifactKind.NODE.value,
        target_name="ChatbotMessage",
        strategy=DIRECT_STRATEGY,
        source_fields=("message_id",),
        fallback_fields=(),
        notes="Chatbot message identity is message_id.",
    ),
    MergeKeySpec(
        source_name="fct_chatbot_tool_calls",
        artifact_kind=GraphArtifactKind.NODE.value,
        target_name="ToolCall",
        strategy=DIRECT_STRATEGY,
        source_fields=("tool_call_id",),
        fallback_fields=(),
        notes="Tool call identity is tool_call_id.",
    ),
    MergeKeySpec(
        source_name="dim_ai_articles",
        artifact_kind=GraphArtifactKind.NODE.value,
        target_name="AIArticle",
        strategy=DIRECT_STRATEGY,
        source_fields=("ai_article_id",),
        fallback_fields=(),
        notes="AI article identity is ai_article_id.",
    ),
    MergeKeySpec(
        source_name="dim_news",
        artifact_kind=GraphArtifactKind.NODE.value,
        target_name="News",
        strategy=DIRECT_STRATEGY,
        source_fields=("news_id",),
        fallback_fields=(),
        notes="News identity is news_id.",
    ),
    MergeKeySpec(
        source_name="dim_notification_content",
        artifact_kind=GraphArtifactKind.NODE.value,
        target_name="NotificationContent",
        strategy=FALLBACK_STRATEGY,
        source_fields=("content_id",),
        fallback_fields=("notification_id",),
        notes="Notification content primarily uses content_id, falling back to notification_id if needed.",
    ),
    MergeKeySpec(
        source_name="dim_subscription_products",
        artifact_kind=GraphArtifactKind.NODE.value,
        target_name="SubscriptionProduct",
        strategy=DIRECT_STRATEGY,
        source_fields=("subscription_type_id",),
        fallback_fields=(),
        notes="Subscription product identity is subscription_type_id.",
    ),
    MergeKeySpec(
        source_name="dim_voucher_catalog",
        artifact_kind=GraphArtifactKind.NODE.value,
        target_name="Voucher",
        strategy=DIRECT_STRATEGY,
        source_fields=("voucher_key",),
        fallback_fields=(),
        notes="Voucher identity is voucher_key.",
    ),
    MergeKeySpec(
        source_name="dim_partner_reward_catalog",
        artifact_kind=GraphArtifactKind.NODE.value,
        target_name="PartnerReward",
        strategy=DIRECT_STRATEGY,
        source_fields=("partner_reward_id",),
        fallback_fields=(),
        notes="Partner reward identity is partner_reward_id.",
    ),
    MergeKeySpec(
        source_name="dim_super6_rounds",
        artifact_kind=GraphArtifactKind.NODE.value,
        target_name="Super6Round",
        strategy=DIRECT_STRATEGY,
        source_fields=("super6_round_id",),
        fallback_fields=(),
        notes="Super6 round identity is super6_round_id.",
    ),
    MergeKeySpec(
        source_name="dim_lms_competitions",
        artifact_kind=GraphArtifactKind.NODE.value,
        target_name="LMSCompetition",
        strategy=DIRECT_STRATEGY,
        source_fields=("competition_id",),
        fallback_fields=(),
        notes="LMS competition identity is competition_id.",
    ),
    MergeKeySpec(
        source_name="dim_fixture_polls",
        artifact_kind=GraphArtifactKind.NODE.value,
        target_name="Poll",
        strategy=DIRECT_STRATEGY,
        source_fields=("poll_id",),
        fallback_fields=(),
        notes="Poll identity is poll_id.",
    ),
    MergeKeySpec(
        source_name="dim_questions",
        artifact_kind=GraphArtifactKind.NODE.value,
        target_name="Question",
        strategy=DIRECT_STRATEGY,
        source_fields=("question_id",),
        fallback_fields=(),
        notes="Question identity is question_id.",
    ),
    MergeKeySpec(
        source_name="dim_quizzes",
        artifact_kind=GraphArtifactKind.NODE.value,
        target_name="Quiz",
        strategy=DIRECT_STRATEGY,
        source_fields=("quiz_id",),
        fallback_fields=(),
        notes="Quiz identity is quiz_id.",
    ),
    MergeKeySpec(
        source_name="dim_quiz_questions_enhanced",
        artifact_kind=GraphArtifactKind.NODE.value,
        target_name="QuizQuestion",
        strategy=DIRECT_STRATEGY,
        source_fields=("quiz_question_id",),
        fallback_fields=(),
        notes="Quiz question identity is quiz_question_id.",
    ),
    MergeKeySpec(
        source_name="dim_tags",
        artifact_kind=GraphArtifactKind.NODE.value,
        target_name="Tag",
        strategy=DIRECT_STRATEGY,
        source_fields=("tag_id",),
        fallback_fields=(),
        notes="Tag identity is tag_id.",
    ),
    MergeKeySpec(
        source_name="fct_sentiment",
        artifact_kind=GraphArtifactKind.NODE.value,
        target_name="Sentiment",
        strategy=SYNTHETIC_HASH_STRATEGY,
        source_fields=("source_type", "item_id", "user_id"),
        fallback_fields=(),
        notes="Sentiment nodes use a stable synthetic key from (source_type, item_id, user_id).",
    ),
    MergeKeySpec(
        source_name="fct_topics",
        artifact_kind=GraphArtifactKind.NODE.value,
        target_name="Topic",
        strategy=DIRECT_STRATEGY,
        source_fields=("id",),
        fallback_fields=(),
        notes="Topic node identity comes from the source row id; canonical topic label resolution is separate.",
    ),
    MergeKeySpec(
        source_name="fct_user_rating_history",
        artifact_kind=GraphArtifactKind.NODE.value,
        target_name="RatingSnapshot",
        strategy=DIRECT_STRATEGY,
        source_fields=("rating_event_id",),
        fallback_fields=(),
        notes="Rating snapshot identity is rating_event_id.",
    ),
    MergeKeySpec(
        source_name="fct_awards_and_achievements",
        artifact_kind=GraphArtifactKind.NODE.value,
        target_name="Achievement",
        strategy=DIRECT_STRATEGY,
        source_fields=("achievement_id",),
        fallback_fields=(),
        notes="Achievement identity is achievement_id.",
    ),
    MergeKeySpec(
        source_name="fct_prediction_duels",
        artifact_kind=GraphArtifactKind.NODE.value,
        target_name="Duel",
        strategy=DIRECT_STRATEGY,
        source_fields=("duel_id",),
        fallback_fields=(),
        notes="Duel identity is duel_id.",
    ),
    MergeKeySpec(
        source_name="dim_private_league_themes",
        artifact_kind=GraphArtifactKind.NODE.value,
        target_name="LeagueTheme",
        strategy=FALLBACK_STRATEGY,
        source_fields=("theme_id",),
        fallback_fields=("private_league_id",),
        notes="Theme identity uses theme_id when trustworthy, otherwise falls back to private_league_id-derived identity.",
    ),
    
    # Relationship sources
    
    MergeKeySpec(
        source_name="fct_predictions",
        artifact_kind=GraphArtifactKind.RELATIONSHIP.value,
        target_name="PREDICTED",
        strategy=DIRECT_STRATEGY,
        source_fields=("prediction_id",),
        fallback_fields=(),
        notes="Prediction edge identity is prediction_id.",
    ),
    MergeKeySpec(
        source_name="dim_private_league_members",
        artifact_kind=GraphArtifactKind.RELATIONSHIP.value,
        target_name="MEMBER_OF",
        strategy=FALLBACK_STRATEGY,
        source_fields=("membership_id",),
        fallback_fields=("private_league_id", "user_id"),
        notes="Membership uses membership_id when present, else falls back to (private_league_id, user_id).",
    ),
    MergeKeySpec(
        source_name="jct_notification_recipients",
        artifact_kind=GraphArtifactKind.RELATIONSHIP.value,
        target_name="RECEIVED_NOTIFICATION",
        strategy=COMPOSITE_STRATEGY,
        source_fields=("notification_id", "user_id"),
        fallback_fields=(),
        notes="Notification delivery edge identity is (notification_id, user_id).",
    ),
    MergeKeySpec(
        source_name="fct_partner_reward_redemptions",
        artifact_kind=GraphArtifactKind.RELATIONSHIP.value,
        target_name="REDEEMED",
        strategy=DIRECT_STRATEGY,
        source_fields=("redemption_id",),
        fallback_fields=(),
        notes="Reward redemption edge identity is redemption_id.",
    ),
    MergeKeySpec(
        source_name="fct_voucher_purchases",
        artifact_kind=GraphArtifactKind.RELATIONSHIP.value,
        target_name="PURCHASED",
        strategy=DIRECT_STRATEGY,
        source_fields=("purchase_id",),
        fallback_fields=(),
        notes="Voucher purchase edge identity is purchase_id.",
    ),
    MergeKeySpec(
        source_name="fct_subscription_lifecycle",
        artifact_kind=GraphArtifactKind.RELATIONSHIP.value,
        target_name="SUBSCRIBED_TO",
        strategy=DIRECT_STRATEGY,
        source_fields=("lifecycle_event_id",),
        fallback_fields=(),
        notes="Subscription lifecycle edge identity is lifecycle_event_id.",
    ),
    MergeKeySpec(
        source_name="fct_team_affinity",
        artifact_kind=GraphArtifactKind.RELATIONSHIP.value,
        target_name="HAS_AFFINITY",
        strategy=DIRECT_STRATEGY,
        source_fields=("affinity_id",),
        fallback_fields=(),
        notes="Affinity edge identity is affinity_id.",
    ),
    MergeKeySpec(
        source_name="fct_super6_participants",
        artifact_kind=GraphArtifactKind.RELATIONSHIP.value,
        target_name="PARTICIPATED_IN",
        strategy=DIRECT_STRATEGY,
        source_fields=("super6_participant_id",),
        fallback_fields=(),
        notes="Super6 participation edge identity is super6_participant_id.",
    ),
    MergeKeySpec(
        source_name="dim_lms_competitions",
        artifact_kind=GraphArtifactKind.RELATIONSHIP.value,
        target_name="PARTICIPATED_IN",
        strategy=COMPOSITE_STRATEGY,
        source_fields=("user_id", "competition_id"),
        fallback_fields=(),
        notes="LMS participation edges use (user_id, competition_id).",
    ),
    MergeKeySpec(
        source_name="dim_super6_round_fixtures",
        artifact_kind=GraphArtifactKind.RELATIONSHIP.value,
        target_name="HAS_FIXTURE",
        strategy=DIRECT_STRATEGY,
        source_fields=("super6_round_fixture_id",),
        fallback_fields=(),
        notes="Round-fixture junction edge identity is super6_round_fixture_id.",
    ),
    MergeKeySpec(
        source_name="fct_discussion_events",
        artifact_kind=GraphArtifactKind.RELATIONSHIP.value,
        target_name="JOINED_DISCUSSION",
        strategy=COMPOSITE_STRATEGY,
        source_fields=("discussion_id", "user_id", "event_type"),
        fallback_fields=(),
        notes="Discussion event edge identity uses a stable composite key.",
    ),
    MergeKeySpec(
        source_name="fct_awards_and_achievements",
        artifact_kind=GraphArtifactKind.RELATIONSHIP.value,
        target_name="ACHIEVED",
        strategy=COMPOSITE_STRATEGY,
        source_fields=("user_id", "achievement_id"),
        fallback_fields=(),
        notes="User achievement edge identity uses (user_id, achievement_id).",
    ),
    MergeKeySpec(
        source_name="dim_posts",
        artifact_kind=GraphArtifactKind.RELATIONSHIP.value,
        target_name="POSTED",
        strategy=COMPOSITE_STRATEGY,
        source_fields=("user_id", "post_id"),
        fallback_fields=(),
        notes="Authorship edge identity uses (user_id, post_id).",
    ),
    MergeKeySpec(
        source_name="dim_comments",
        artifact_kind=GraphArtifactKind.RELATIONSHIP.value,
        target_name="COMMENTED",
        strategy=COMPOSITE_STRATEGY,
        source_fields=("user_id", "comment_id"),
        fallback_fields=(),
        notes="Comment authorship edge identity uses (user_id, comment_id).",
    ),
    MergeKeySpec(
        source_name="fct_coin_transactions",
        artifact_kind=GraphArtifactKind.RELATIONSHIP.value,
        target_name="SPENT",
        strategy=DIRECT_STRATEGY,
        source_fields=("event_id",),
        fallback_fields=(),
        notes="Spend relationship identity is transaction_id.",
    ),
    MergeKeySpec(
        source_name="dim_private_league_themes",
        artifact_kind=GraphArtifactKind.RELATIONSHIP.value,
        target_name="HAS_THEME",
        strategy=COMPOSITE_STRATEGY,
        source_fields=("private_league_id", "theme_id"),
        fallback_fields=("private_league_id",),
        notes="HAS_THEME uses (private_league_id, theme_id), with fallback when theme_id is unstable.",
    ),
    MergeKeySpec(
        source_name="dim_prediction_discussions",
        artifact_kind=GraphArtifactKind.RELATIONSHIP.value,
        target_name="ABOUT",
        strategy=COMPOSITE_STRATEGY,
        source_fields=("prediction_discussion_id", "fixture_id"),
        fallback_fields=(),
        notes="Prediction discussion context edge uses (prediction_discussion_id, fixture_id).",
    ),
    MergeKeySpec(
        source_name="dim_posts",
        artifact_kind=GraphArtifactKind.RELATIONSHIP.value,
        target_name="HAS_TAG",
        strategy=COMPOSITE_STRATEGY,
        source_fields=("post_id", "tag_id"),
        fallback_fields=(),
        notes="Post tagging edge uses (post_id, tag_id).",
    ),
    MergeKeySpec(
        source_name="dim_news",
        artifact_kind=GraphArtifactKind.RELATIONSHIP.value,
        target_name="HAS_TAG",
        strategy=COMPOSITE_STRATEGY,
        source_fields=("news_id", "tag_id"),
        fallback_fields=(),
        notes="News tagging edge uses (news_id, tag_id).",
    ),
    MergeKeySpec(
        source_name="dim_ai_articles",
        artifact_kind=GraphArtifactKind.RELATIONSHIP.value,
        target_name="HAS_TAG",
        strategy=COMPOSITE_STRATEGY,
        source_fields=("ai_article_id", "tag_id"),
        fallback_fields=(),
        notes="AI article tagging edge uses (ai_article_id, tag_id).",
    ),
    MergeKeySpec(
        source_name="dim_fixtures",
        artifact_kind=GraphArtifactKind.RELATIONSHIP.value,
        target_name="HOME_TEAM",
        strategy=COMPOSITE_STRATEGY,
        source_fields=("fixture_id", "home_team_id"),
        fallback_fields=(),
        notes="HOME_TEAM edge identity uses (fixture_id, home_team_id).",
    ),
    MergeKeySpec(
        source_name="dim_fixtures",
        artifact_kind=GraphArtifactKind.RELATIONSHIP.value,
        target_name="AWAY_TEAM",
        strategy=COMPOSITE_STRATEGY,
        source_fields=("fixture_id", "away_team_id"),
        fallback_fields=(),
        notes="AWAY_TEAM edge identity uses (fixture_id, away_team_id).",
    ),
    MergeKeySpec(
        source_name="dim_fixtures",
        artifact_kind=GraphArtifactKind.RELATIONSHIP.value,
        target_name="IN_LEAGUE",
        strategy=COMPOSITE_STRATEGY,
        source_fields=("fixture_id", "league_id"),
        fallback_fields=(),
        notes="IN_LEAGUE edge identity uses (fixture_id, league_id).",
    ),
    
    # Enrichment sources
    
    MergeKeySpec(
        source_name="dim_teams_enhanced",
        artifact_kind=GraphArtifactKind.ENRICHMENT.value,
        target_name="Team",
        strategy=DIRECT_STRATEGY,
        source_fields=("team_id",),
        fallback_fields=(),
        notes="Team enrichment targets Team by team_id.",
    ),
    MergeKeySpec(
        source_name="dim_questions_enhanced",
        artifact_kind=GraphArtifactKind.ENRICHMENT.value,
        target_name="Question",
        strategy=DIRECT_STRATEGY,
        source_fields=("question_id",),
        fallback_fields=(),
        notes="Question enrichment targets Question by question_id.",
    ),
    MergeKeySpec(
        source_name="dim_notification_preferences",
        artifact_kind=GraphArtifactKind.ENRICHMENT.value,
        target_name="User",
        strategy=DIRECT_STRATEGY,
        source_fields=("user_id",),
        fallback_fields=(),
        notes="Notification preferences enrich User by user_id.",
    ),
    MergeKeySpec(
        source_name="fct_partner_reward_inventory",
        artifact_kind=GraphArtifactKind.ENRICHMENT.value,
        target_name="PartnerReward",
        strategy=DIRECT_STRATEGY,
        source_fields=("partner_reward_id",),
        fallback_fields=(),
        notes="Inventory enriches PartnerReward by partner_reward_id.",
    ),
    MergeKeySpec(
        source_name="fct_user_activities",
        artifact_kind=GraphArtifactKind.ENRICHMENT.value,
        target_name="User",
        strategy=DIRECT_STRATEGY,
        source_fields=("user_id",),
        fallback_fields=(),
        notes="User activities enrich User by user_id.",
    ),
    MergeKeySpec(
        source_name="fct_user_behavior",
        artifact_kind=GraphArtifactKind.ENRICHMENT.value,
        target_name="PersonaState",
        strategy=DIRECT_STRATEGY,
        source_fields=("user_id",),
        fallback_fields=(),
        notes="Behavior enrichment targets PersonaState by user_id in temporal materialization.",
    ),
    MergeKeySpec(
        source_name="fct_user_activities",
        artifact_kind=GraphArtifactKind.RELATIONSHIP.value,
        target_name="LIKED",
        strategy=COMPOSITE_STRATEGY,
        source_fields=("user_id", "activity_id"),
        fallback_fields=(),
        notes="Like edge identity uses (user_id, activity_id) — activity_id is stable per event.",
    ),
    MergeKeySpec(
        source_name="fct_user_activities",
        artifact_kind=GraphArtifactKind.RELATIONSHIP.value,
        target_name="ANSWERED",
        strategy=COMPOSITE_STRATEGY,
        source_fields=("user_id", "activity_id"),
        fallback_fields=(),
        notes="Poll answer edge identity uses (user_id, activity_id).",
    ),
    MergeKeySpec(
        source_name="fct_user_activities",
        artifact_kind=GraphArtifactKind.RELATIONSHIP.value,
        target_name="FRIENDED",
        strategy=COMPOSITE_STRATEGY,
        source_fields=("user_id", "activity_id"),
        fallback_fields=(),
        notes="Friend edge identity uses (user_id, activity_id).",
    ),

)

_MERGE_KEY_INDEX: dict[tuple[str, str], MergeKeySpec] = {
    (spec.source_name, spec.target_name): spec for spec in MERGE_KEY_SPECS
}


def get_merge_key_spec(source_name: str, target_name: str) -> MergeKeySpec:
    """
    Return the merge-key spec for a source/target pair.

    Args:
        source_name: Logical source/table name.
        target_name: Graph target label or relationship type.

    Returns:
        MergeKeySpec.

    Raises:
        KeyError: If no spec is registered for the pair.
    """
    return _MERGE_KEY_INDEX[(source_name, target_name)]


def requires_synthetic_key(spec: MergeKeySpec) -> bool:
    """
    Return True if the spec uses a synthetic hash strategy.
    """
    return spec.strategy == SYNTHETIC_HASH_STRATEGY


def get_primary_merge_fields(spec: MergeKeySpec) -> tuple[str, ...]:
    """
    Return the primary source fields used by the merge-key strategy.
    """
    return spec.source_fields


def validate_merge_key_specs() -> list[str]:
    """
    Validate all registered merge-key specs.

    Checks:
    - source_name is non-empty
    - artifact_kind is valid
    - target_name is non-empty
    - strategy is valid
    - direct/composite strategies declare source_fields
    - fallback strategies declare fallback_fields
    - synthetic strategies justify themselves in notes
    - declared source fields exist in the warehouse schema when runtime
      schema introspection is possible
    - there are no duplicate (source_name, target_name) registrations

    Returns:
        Flat list of validation error strings. Empty list means valid.
    """
    errors: list[str] = []
    seen_keys: set[tuple[str, str]] = set()

    valid_artifact_kinds = {
        GraphArtifactKind.NODE.value,
        GraphArtifactKind.RELATIONSHIP.value,
        GraphArtifactKind.ENRICHMENT.value,
    }

    schema_fields_by_source = _get_warehouse_schema_fields()

    for idx, spec in enumerate(MERGE_KEY_SPECS):
        prefix = (
            f"MERGE_KEY_SPECS[{idx}] "
            f"(source={spec.source_name!r}, target={spec.target_name!r})"
        )

        if not spec.source_name or not spec.source_name.strip():
            errors.append(f"{prefix}: source_name cannot be empty")

        if spec.artifact_kind not in valid_artifact_kinds:
            errors.append(
                f"{prefix}: artifact_kind '{spec.artifact_kind}' "
                f"must be one of {sorted(valid_artifact_kinds)}"
            )

        if not spec.target_name or not spec.target_name.strip():
            errors.append(f"{prefix}: target_name cannot be empty")

        if spec.strategy not in VALID_MERGE_KEY_STRATEGIES:
            errors.append(
                f"{prefix}: strategy '{spec.strategy}' must be one of "
                f"{sorted(VALID_MERGE_KEY_STRATEGIES)}"
            )

        duplicate_key = (spec.source_name, spec.target_name)
        if duplicate_key in seen_keys:
            errors.append(
                f"{prefix}: duplicate merge-key registration for source/target pair"
            )
        seen_keys.add(duplicate_key)

        if spec.strategy in {DIRECT_STRATEGY, COMPOSITE_STRATEGY}:
            if not spec.source_fields:
                errors.append(
                    f"{prefix}: strategy '{spec.strategy}' requires at least one source field"
                )

        if spec.strategy == FALLBACK_STRATEGY:
            if not spec.source_fields:
                errors.append(
                    f"{prefix}: fallback strategy requires primary source_fields"
                )
            if not spec.fallback_fields:
                errors.append(
                    f"{prefix}: fallback strategy requires fallback_fields"
                )

        if spec.strategy == SYNTHETIC_HASH_STRATEGY:
            if not spec.source_fields:
                errors.append(
                    f"{prefix}: synthetic_hash strategy requires source_fields"
                )
            if spec.notes is None or not spec.notes.strip():
                errors.append(
                    f"{prefix}: synthetic_hash strategy must be justified in notes"
                )

        if any(not field or not field.strip() for field in spec.source_fields):
            errors.append(
                f"{prefix}: source_fields cannot contain empty values"
            )

        if any(not field or not field.strip() for field in spec.fallback_fields):
            errors.append(
                f"{prefix}: fallback_fields cannot contain empty values"
            )

        if spec.source_name in schema_fields_by_source:
            known_fields = schema_fields_by_source[spec.source_name]
            for field_name in spec.source_fields:
                if field_name not in known_fields:
                    errors.append(
                        f"{prefix}: source field '{field_name}' not found in warehouse schema for '{spec.source_name}'"
                    )
            for field_name in spec.fallback_fields:
                if field_name not in known_fields:
                    errors.append(
                        f"{prefix}: fallback field '{field_name}' not found in warehouse schema for '{spec.source_name}'"
                    )

    return errors


def _get_warehouse_schema_fields() -> dict[str, set[str]]:
    """
    Best-effort runtime introspection of warehouse schema row fields.

    Returns:
        Mapping of source_name -> set of known row field names.

    This function is intentionally defensive. It supports validation when
    warehouse schema modules are importable but degrades gracefully when they
    are not yet available.
    """
    schemas: dict[str, set[str]] = {}

    try:
        import app.schemas.warehouse as warehouse_pkg  # type: ignore
    except Exception:
        return schemas

    pkg_dict = getattr(warehouse_pkg, "__dict__", {})
    for module_name, module_value in pkg_dict.items():
        if module_name.startswith("_"):
            continue

        source_name = getattr(module_value, "SOURCE_NAME", None)
        if source_name is None:
            continue

        row_cls = _find_row_dataclass(module_value)
        if row_cls is None:
            continue

        annotations = getattr(row_cls, "__annotations__", {})
        field_names = {name for name in annotations.keys() if name.strip()}
        if field_names:
            schemas[str(source_name)] = field_names

    return schemas


def _find_row_dataclass(module_value: Any) -> type[Any] | None:
    """
    Best-effort discovery of a warehouse row dataclass inside a schema module.

    Convention used in the codebase:
    - exactly one primary *Row dataclass per schema module
    - dataclass has a from_row classmethod and __annotations__
    """
    module_dict = getattr(module_value, "__dict__", {})
    for _, obj in module_dict.items():
        if not isinstance(obj, type):
            continue

        has_annotations = bool(getattr(obj, "__annotations__", {}))
        has_from_row = callable(getattr(obj, "from_row", None))
        if has_annotations and has_from_row:
            return obj

    return None