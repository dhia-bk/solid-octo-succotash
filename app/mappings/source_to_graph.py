"""
Source → graph artifact routing declarations.

This module defines how each warehouse source maps at a high level to graph
artifacts (nodes, relationships, enrichment, or no graph output).

It is the routing layer of the mapping system and answers:

- Does this source emit graph records?
- If yes, what kind of artifact does it produce (node, relationship, enrichment)?
- What graph label or relationship type does it target?
- What graph contract class represents the output?
- What inclusion mode governs this source?

This module does NOT define:
- field-level mappings (handled in mapping specs)
- endpoint resolution (handled in endpoint_resolution.py)
- merge key strategy (handled in merge_keys.py)
- property ownership (handled in property_ownership.py)

Those concerns are intentionally separated.

Design rules:
- This file is the single executable source-of-truth for source → graph routing.
- Every graph-producing or graph-enriching source must be declared here.
- Feature-only and serving-only sources must be explicitly marked as
  emits_records = False.
- A source may emit multiple artifacts (e.g., node + relationship), and each
  must have its own declaration entry.
- This module must not import transformers or domain mapping logic.

Validation guarantees:
- source_name must exist in the source inventory registry when that registry
  can be introspected at runtime
- inclusion_mode must match SOURCE_INCLUSION_CATEGORIES
- artifact_kind must be one of GraphArtifactKind values, or "none" for
  explicit non-emitting sources
- graph-producing sources must declare a valid target label or relationship type
- declared labels must exist in GRAPH_NODE_LABELS
- declared relationship types must exist in GRAPH_RELATIONSHIP_TYPES
- non-emitting sources must not declare graph contracts

Primary outputs:
- SOURCE_ARTIFACT_DECLARATIONS: the full registry of source routing rules
- lookup helpers to query routing behavior per source
- validation helpers to ensure mapping completeness and correctness

This module allows transformers and pipelines to determine what a source is
allowed to produce without inspecting warehouse schemas or hardcoding logic.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.core.constants import (
    FEATURE_SOURCE,
    GRAPH_CORE,
    GRAPH_ENRICHMENT,
    GRAPH_NODE_LABELS,
    GRAPH_RELATIONSHIP_TYPES,
    SERVING_ONLY,
    SOURCE_INCLUSION_CATEGORIES,
)
from app.mappings.base import GraphArtifactKind

# Explicit internal marker for sources that do not emit graph records.
NON_EMITTING_ARTIFACT_KIND: str = "none"


@dataclass(frozen=True)
class SourceArtifactDeclaration:
    """
    High-level routing declaration for one source → graph artifact mapping.

    Attributes:
        source_name: Logical warehouse source/table name.
        artifact_kind: "node", "relationship", "enrichment", or "none".
        target_label_or_rel: Graph node label or relationship type. Must be
            blank for non-emitting sources.
        graph_contract_name: Target graph contract class name. Must be blank for
            non-emitting sources.
        inclusion_mode: Source inclusion category.
        emits_records: False for FEATURE_SOURCE / SERVING_ONLY / excluded-like
            sources that never produce graph write records.
        notes: Optional explanatory notes for maintainers.
    """

    source_name: str
    artifact_kind: str
    target_label_or_rel: str
    graph_contract_name: str
    inclusion_mode: str
    emits_records: bool
    notes: str | None


# Core node declarations

CORE_NODE_DECLARATIONS: tuple[SourceArtifactDeclaration, ...] = (
    SourceArtifactDeclaration(
        source_name="dim_users",
        artifact_kind=GraphArtifactKind.NODE.value,
        target_label_or_rel="User",
        graph_contract_name="UserNode",
        inclusion_mode=GRAPH_CORE,
        emits_records=True,
        notes="Primary identity backbone for all user-centric graph structures.",
    ),
    SourceArtifactDeclaration(
        source_name="dim_avatars",
        artifact_kind=GraphArtifactKind.NODE.value,
        target_label_or_rel="Avatar",
        graph_contract_name="AvatarNode",
        inclusion_mode=GRAPH_CORE,
        emits_records=True,
        notes="Avatar catalog nodes.",
    ),
    SourceArtifactDeclaration(
        source_name="dim_badges",
        artifact_kind=GraphArtifactKind.NODE.value,
        target_label_or_rel="Badge",
        graph_contract_name="BadgeNode",
        inclusion_mode=GRAPH_CORE,
        emits_records=True,
        notes="Badge catalog nodes.",
    ),
    SourceArtifactDeclaration(
        source_name="dim_teams",
        artifact_kind=GraphArtifactKind.NODE.value,
        target_label_or_rel="Team",
        graph_contract_name="TeamNode",
        inclusion_mode=GRAPH_CORE,
        emits_records=True,
        notes="Canonical team identity source.",
    ),
    SourceArtifactDeclaration(
        source_name="dim_leagues",
        artifact_kind=GraphArtifactKind.NODE.value,
        target_label_or_rel="League",
        graph_contract_name="LeagueNode",
        inclusion_mode=GRAPH_CORE,
        emits_records=True,
        notes="Canonical competition league source.",
    ),
    SourceArtifactDeclaration(
        source_name="dim_fixtures",
        artifact_kind=GraphArtifactKind.NODE.value,
        target_label_or_rel="Match",
        graph_contract_name="MatchNode",
        inclusion_mode=GRAPH_CORE,
        emits_records=True,
        notes="Canonical match / fixture source.",
    ),
    SourceArtifactDeclaration(
        source_name="dim_private_leagues",
        artifact_kind=GraphArtifactKind.NODE.value,
        target_label_or_rel="PrivateLeague",
        graph_contract_name="PrivateLeagueNode",
        inclusion_mode=GRAPH_CORE,
        emits_records=True,
        notes="Primary social grouping node source.",
    ),
    SourceArtifactDeclaration(
        source_name="dim_posts",
        artifact_kind=GraphArtifactKind.NODE.value,
        target_label_or_rel="Post",
        graph_contract_name="PostNode",
        inclusion_mode=GRAPH_CORE,
        emits_records=True,
        notes="User-generated post node source.",
    ),
    SourceArtifactDeclaration(
        source_name="dim_comments",
        artifact_kind=GraphArtifactKind.NODE.value,
        target_label_or_rel="Comment",
        graph_contract_name="CommentNode",
        inclusion_mode=GRAPH_CORE,
        emits_records=True,
        notes="Comment node source.",
    ),
    SourceArtifactDeclaration(
        source_name="dim_discussions",
        artifact_kind=GraphArtifactKind.NODE.value,
        target_label_or_rel="Discussion",
        graph_contract_name="DiscussionNode",
        inclusion_mode=GRAPH_CORE,
        emits_records=True,
        notes="Fixture or content discussion threads.",
    ),
    SourceArtifactDeclaration(
        source_name="dim_prediction_discussions",
        artifact_kind=GraphArtifactKind.NODE.value,
        target_label_or_rel="PredictionDiscussion",
        graph_contract_name="PredictionDiscussionNode",
        inclusion_mode=GRAPH_CORE,
        emits_records=True,
        notes="Prediction-specific discussion threads.",
    ),
    SourceArtifactDeclaration(
        source_name="dim_chat_conversations_mysql",
        artifact_kind=GraphArtifactKind.NODE.value,
        target_label_or_rel="Conversation",
        graph_contract_name="ConversationNode",
        inclusion_mode=GRAPH_CORE,
        emits_records=True,
        notes="Social chat conversation nodes.",
    ),
    SourceArtifactDeclaration(
        source_name="dim_chat_direct_pairs",
        artifact_kind=GraphArtifactKind.NODE.value,
        target_label_or_rel="DirectPair",
        graph_contract_name="DirectPairNode",
        inclusion_mode=GRAPH_CORE,
        emits_records=True,
        notes="Direct-message pair nodes.",
    ),
    SourceArtifactDeclaration(
        source_name="dim_chatbot_conversations",
        artifact_kind=GraphArtifactKind.NODE.value,
        target_label_or_rel="ChatbotConversation",
        graph_contract_name="ChatbotConversationNode",
        inclusion_mode=GRAPH_CORE,
        emits_records=True,
        notes="AI/chatbot conversation nodes.",
    ),
    SourceArtifactDeclaration(
        source_name="fct_chatbot_messages",
        artifact_kind=GraphArtifactKind.NODE.value,
        target_label_or_rel="ChatbotMessage",
        graph_contract_name="ChatbotMessageNode",
        inclusion_mode=GRAPH_CORE,
        emits_records=True,
        notes="Chatbot message nodes.",
    ),
    SourceArtifactDeclaration(
        source_name="fct_chatbot_tool_calls",
        artifact_kind=GraphArtifactKind.NODE.value,
        target_label_or_rel="ToolCall",
        graph_contract_name="ToolCallNode",
        inclusion_mode=GRAPH_CORE,
        emits_records=True,
        notes="Chatbot tool call nodes.",
    ),
    SourceArtifactDeclaration(
        source_name="dim_ai_articles",
        artifact_kind=GraphArtifactKind.NODE.value,
        target_label_or_rel="AIArticle",
        graph_contract_name="AIArticleNode",
        inclusion_mode=GRAPH_CORE,
        emits_records=True,
        notes="AI-generated article nodes.",
    ),
    SourceArtifactDeclaration(
        source_name="dim_news",
        artifact_kind=GraphArtifactKind.NODE.value,
        target_label_or_rel="News",
        graph_contract_name="NewsNode",
        inclusion_mode=GRAPH_CORE,
        emits_records=True,
        notes="Editorial/news content nodes.",
    ),
    SourceArtifactDeclaration(
        source_name="dim_notification_content",
        artifact_kind=GraphArtifactKind.NODE.value,
        target_label_or_rel="NotificationContent",
        graph_contract_name="NotificationContentNode",
        inclusion_mode=GRAPH_CORE,
        emits_records=True,
        notes="Notification payload/content nodes.",
    ),
    SourceArtifactDeclaration(
        source_name="dim_subscription_products",
        artifact_kind=GraphArtifactKind.NODE.value,
        target_label_or_rel="SubscriptionProduct",
        graph_contract_name="SubscriptionProductNode",
        inclusion_mode=GRAPH_CORE,
        emits_records=True,
        notes="Subscription tier catalog nodes.",
    ),
    SourceArtifactDeclaration(
        source_name="dim_voucher_catalog",
        artifact_kind=GraphArtifactKind.NODE.value,
        target_label_or_rel="Voucher",
        graph_contract_name="VoucherNode",
        inclusion_mode=GRAPH_CORE,
        emits_records=True,
        notes="Voucher catalog nodes.",
    ),
    SourceArtifactDeclaration(
        source_name="dim_partner_reward_catalog",
        artifact_kind=GraphArtifactKind.NODE.value,
        target_label_or_rel="PartnerReward",
        graph_contract_name="PartnerRewardNode",
        inclusion_mode=GRAPH_CORE,
        emits_records=True,
        notes="Partner reward catalog nodes.",
    ),
    SourceArtifactDeclaration(
        source_name="dim_super6_rounds",
        artifact_kind=GraphArtifactKind.NODE.value,
        target_label_or_rel="Super6Round",
        graph_contract_name="Super6RoundNode",
        inclusion_mode=GRAPH_CORE,
        emits_records=True,
        notes="Super6 round nodes.",
    ),
    SourceArtifactDeclaration(
        source_name="dim_lms_competitions",
        artifact_kind=GraphArtifactKind.NODE.value,
        target_label_or_rel="LMSCompetition",
        graph_contract_name="LMSCompetitionNode",
        inclusion_mode=GRAPH_CORE,
        emits_records=True,
        notes="LMS competition nodes.",
    ),
    SourceArtifactDeclaration(
        source_name="dim_fixture_polls",
        artifact_kind=GraphArtifactKind.NODE.value,
        target_label_or_rel="Poll",
        graph_contract_name="PollNode",
        inclusion_mode=GRAPH_CORE,
        emits_records=True,
        notes="Fixture poll nodes.",
    ),
    SourceArtifactDeclaration(
        source_name="dim_questions",
        artifact_kind=GraphArtifactKind.NODE.value,
        target_label_or_rel="Question",
        graph_contract_name="QuestionNode",
        inclusion_mode=GRAPH_CORE,
        emits_records=True,
        notes="Question catalog nodes.",
    ),
    SourceArtifactDeclaration(
        source_name="dim_quizzes",
        artifact_kind=GraphArtifactKind.NODE.value,
        target_label_or_rel="Quiz",
        graph_contract_name="QuizNode",
        inclusion_mode=GRAPH_CORE,
        emits_records=True,
        notes="Quiz catalog nodes.",
    ),
    SourceArtifactDeclaration(
        source_name="dim_quiz_questions_enhanced",
        artifact_kind=GraphArtifactKind.NODE.value,
        target_label_or_rel="QuizQuestion",
        graph_contract_name="QuizQuestionNode",
        inclusion_mode=GRAPH_CORE,
        emits_records=True,
        notes="Quiz question nodes.",
    ),
    SourceArtifactDeclaration(
        source_name="dim_tags",
        artifact_kind=GraphArtifactKind.NODE.value,
        target_label_or_rel="Tag",
        graph_contract_name="TagNode",
        inclusion_mode=GRAPH_CORE,
        emits_records=True,
        notes="Tag catalog nodes.",
    ),
    SourceArtifactDeclaration(
        source_name="fct_sentiment",
        artifact_kind=GraphArtifactKind.NODE.value,
        target_label_or_rel="Sentiment",
        graph_contract_name="SentimentNode",
        inclusion_mode=GRAPH_CORE,
        emits_records=True,
        notes="ML-derived sentiment nodes.",
    ),
    SourceArtifactDeclaration(
        source_name="fct_topics",
        artifact_kind=GraphArtifactKind.NODE.value,
        target_label_or_rel="Topic",
        graph_contract_name="TopicNode",
        inclusion_mode=GRAPH_CORE,
        emits_records=True,
        notes="ML-derived topic nodes.",
    ),
    SourceArtifactDeclaration(
        source_name="fct_user_rating_history",
        artifact_kind=GraphArtifactKind.NODE.value,
        target_label_or_rel="RatingSnapshot",
        graph_contract_name="RatingSnapshotNode",
        inclusion_mode=GRAPH_CORE,
        emits_records=True,
        notes="User duel rating snapshot nodes.",
    ),
    SourceArtifactDeclaration(
        source_name="fct_awards_and_achievements",
        artifact_kind=GraphArtifactKind.NODE.value,
        target_label_or_rel="Achievement",
        graph_contract_name="AchievementNode",
        inclusion_mode=GRAPH_CORE,
        emits_records=True,
        notes="Achievement nodes fed by awards/achievements source.",
    ),
    SourceArtifactDeclaration(
        source_name="fct_prediction_duels",
        artifact_kind=GraphArtifactKind.NODE.value,
        target_label_or_rel="Duel",
        graph_contract_name="DuelNode",
        inclusion_mode=GRAPH_CORE,
        emits_records=True,
        notes="Prediction duel nodes.",
    ),
)

# Relationship declarations

RELATIONSHIP_DECLARATIONS: tuple[SourceArtifactDeclaration, ...] = (
    SourceArtifactDeclaration(
        source_name="fct_predictions",
        artifact_kind=GraphArtifactKind.RELATIONSHIP.value,
        target_label_or_rel="PREDICTED",
        graph_contract_name="PredictedRel",
        inclusion_mode=GRAPH_CORE,
        emits_records=True,
        notes="Primary user → match prediction relationship source.",
    ),
    SourceArtifactDeclaration(
        source_name="dim_private_league_members",
        artifact_kind=GraphArtifactKind.RELATIONSHIP.value,
        target_label_or_rel="MEMBER_OF",
        graph_contract_name="MemberOfRel",
        inclusion_mode=GRAPH_CORE,
        emits_records=True,
        notes="User → private league membership source.",
    ),
    SourceArtifactDeclaration(
        source_name="jct_notification_recipients",
        artifact_kind=GraphArtifactKind.RELATIONSHIP.value,
        target_label_or_rel="RECEIVED_NOTIFICATION",
        graph_contract_name="ReceivedNotificationRel",
        inclusion_mode=GRAPH_CORE,
        emits_records=True,
        notes="User → notification content delivery/read relationship source.",
    ),
    SourceArtifactDeclaration(
        source_name="fct_partner_reward_redemptions",
        artifact_kind=GraphArtifactKind.RELATIONSHIP.value,
        target_label_or_rel="REDEEMED",
        graph_contract_name="RedeemedRel",
        inclusion_mode=GRAPH_CORE,
        emits_records=True,
        notes="User → partner reward redemption source.",
    ),
    SourceArtifactDeclaration(
        source_name="fct_voucher_purchases",
        artifact_kind=GraphArtifactKind.RELATIONSHIP.value,
        target_label_or_rel="PURCHASED",
        graph_contract_name="PurchasedRel",
        inclusion_mode=GRAPH_CORE,
        emits_records=True,
        notes="User → voucher purchase source.",
    ),
    SourceArtifactDeclaration(
        source_name="fct_subscription_lifecycle",
        artifact_kind=GraphArtifactKind.RELATIONSHIP.value,
        target_label_or_rel="SUBSCRIBED_TO",
        graph_contract_name="SubscribedToRel",
        inclusion_mode=GRAPH_CORE,
        emits_records=True,
        notes="User → subscription product lifecycle edge source.",
    ),
    SourceArtifactDeclaration(
        source_name="fct_team_affinity",
        artifact_kind=GraphArtifactKind.RELATIONSHIP.value,
        target_label_or_rel="HAS_AFFINITY",
        graph_contract_name="HasAffinityRel",
        inclusion_mode=GRAPH_CORE,
        emits_records=True,
        notes="User → team affinity edge source.",
    ),
    SourceArtifactDeclaration(
        source_name="fct_super6_participants",
        artifact_kind=GraphArtifactKind.RELATIONSHIP.value,
        target_label_or_rel="PARTICIPATED_IN",
        graph_contract_name="ParticipatedInRel",
        inclusion_mode=GRAPH_CORE,
        emits_records=True,
        notes="User → Super6Round participation edge source.",
    ),
    SourceArtifactDeclaration(
        source_name="dim_super6_round_fixtures",
        artifact_kind=GraphArtifactKind.RELATIONSHIP.value,
        target_label_or_rel="HAS_FIXTURE",
        graph_contract_name="HasFixtureRel",
        inclusion_mode=GRAPH_CORE,
        emits_records=True,
        notes="Super6Round → Match junction source.",
    ),
    SourceArtifactDeclaration(
        source_name="fct_discussion_events",
        artifact_kind=GraphArtifactKind.RELATIONSHIP.value,
        target_label_or_rel="JOINED_DISCUSSION",
        graph_contract_name="JoinedDiscussionRel",
        inclusion_mode=GRAPH_CORE,
        emits_records=True,
        notes="User → discussion participation source.",
    ),
    SourceArtifactDeclaration(
        source_name="fct_awards_and_achievements",
        artifact_kind=GraphArtifactKind.RELATIONSHIP.value,
        target_label_or_rel="ACHIEVED",
        graph_contract_name="AchievedRel",
        inclusion_mode=GRAPH_CORE,
        emits_records=True,
        notes="User → achievement edge source.",
    ),
    SourceArtifactDeclaration(
        source_name="dim_posts",
        artifact_kind=GraphArtifactKind.RELATIONSHIP.value,
        target_label_or_rel="POSTED",
        graph_contract_name="PostedRel",
        inclusion_mode=GRAPH_CORE,
        emits_records=True,
        notes="User → post authoring relationship.",
    ),
    SourceArtifactDeclaration(
        source_name="dim_comments",
        artifact_kind=GraphArtifactKind.RELATIONSHIP.value,
        target_label_or_rel="COMMENTED",
        graph_contract_name="CommentedRel",
        inclusion_mode=GRAPH_CORE,
        emits_records=True,
        notes="User → comment authoring relationship.",
    ),
    SourceArtifactDeclaration(
        source_name="fct_coin_transactions",
        artifact_kind=GraphArtifactKind.RELATIONSHIP.value,
        target_label_or_rel="SPENT",
        graph_contract_name="SpentRel",
        inclusion_mode=GRAPH_CORE,
        emits_records=True,
        notes="User → economy target spending relationship where modeled.",
    ),
    SourceArtifactDeclaration(
        source_name="dim_private_league_themes",
        artifact_kind=GraphArtifactKind.RELATIONSHIP.value,
        target_label_or_rel="HAS_THEME",
        graph_contract_name="HasThemeRel",
        inclusion_mode=GRAPH_ENRICHMENT,
        emits_records=True,
        notes="PrivateLeague → LeagueTheme edge source.",
    ),
    SourceArtifactDeclaration(
        source_name="dim_prediction_discussions",
        artifact_kind=GraphArtifactKind.RELATIONSHIP.value,
        target_label_or_rel="ABOUT",
        graph_contract_name="AboutRel",
        inclusion_mode=GRAPH_CORE,
        emits_records=True,
        notes="PredictionDiscussion → Match contextual relationship.",
    ),
    SourceArtifactDeclaration(
        source_name="fct_user_activities",
        artifact_kind=GraphArtifactKind.RELATIONSHIP.value,
        target_label_or_rel="LIKED",
        graph_contract_name="LikedRel",
        inclusion_mode=GRAPH_ENRICHMENT,
        emits_records=True,
        notes="User → Post or User → Comment like activity edges.",
    ),
    SourceArtifactDeclaration(
        source_name="fct_user_activities",
        artifact_kind=GraphArtifactKind.RELATIONSHIP.value,
        target_label_or_rel="ANSWERED",
        graph_contract_name="AnsweredRel",
        inclusion_mode=GRAPH_ENRICHMENT,
        emits_records=True,
        notes="User → Poll fixture poll answer activity edges.",
    ),
    SourceArtifactDeclaration(
        source_name="fct_user_activities",
        artifact_kind=GraphArtifactKind.RELATIONSHIP.value,
        target_label_or_rel="FRIENDED",
        graph_contract_name="FriendedRel",
        inclusion_mode=GRAPH_ENRICHMENT,
        emits_records=True,
        notes="User → User friend added activity edges.",
    ),
)

# Enrichment declarations

ENRICHMENT_DECLARATIONS: tuple[SourceArtifactDeclaration, ...] = (
    SourceArtifactDeclaration(
        source_name="dim_teams_enhanced",
        artifact_kind=GraphArtifactKind.ENRICHMENT.value,
        target_label_or_rel="Team",
        graph_contract_name="TeamNode",
        inclusion_mode=GRAPH_ENRICHMENT,
        emits_records=True,
        notes="Fan analytics enrichment for Team nodes.",
    ),
    SourceArtifactDeclaration(
        source_name="dim_questions_enhanced",
        artifact_kind=GraphArtifactKind.ENRICHMENT.value,
        target_label_or_rel="Question",
        graph_contract_name="QuestionNode",
        inclusion_mode=GRAPH_ENRICHMENT,
        emits_records=True,
        notes="Question analytics enrichment source.",
    ),
    SourceArtifactDeclaration(
        source_name="dim_notification_preferences",
        artifact_kind=GraphArtifactKind.ENRICHMENT.value,
        target_label_or_rel="User",
        graph_contract_name="UserNode",
        inclusion_mode=GRAPH_ENRICHMENT,
        emits_records=True,
        notes="Notification preference enrichment for User nodes.",
    ),
    SourceArtifactDeclaration(
        source_name="fct_partner_reward_inventory",
        artifact_kind=GraphArtifactKind.ENRICHMENT.value,
        target_label_or_rel="PartnerReward",
        graph_contract_name="PartnerRewardNode",
        inclusion_mode=GRAPH_ENRICHMENT,
        emits_records=True,
        notes="Partner reward inventory and stock enrichment.",
    ),
    SourceArtifactDeclaration(
        source_name="fct_user_activities",
        artifact_kind=GraphArtifactKind.ENRICHMENT.value,
        target_label_or_rel="User",
        graph_contract_name="UserNode",
        inclusion_mode=GRAPH_ENRICHMENT,
        emits_records=True,
        notes="Activity-weight and activity-signal enrichment for users.",
    ),
    SourceArtifactDeclaration(
        source_name="fct_user_behavior",
        artifact_kind=GraphArtifactKind.ENRICHMENT.value,
        target_label_or_rel="PersonaState",
        graph_contract_name="PersonaStateNode",
        inclusion_mode=GRAPH_ENRICHMENT,
        emits_records=True,
        notes="Behavior model enrichment input to persona state materialization.",
    ),
    SourceArtifactDeclaration(
        source_name="dim_private_league_themes",
        artifact_kind=GraphArtifactKind.ENRICHMENT.value,
        target_label_or_rel="LeagueTheme",
        graph_contract_name="LeagueThemeNode",
        inclusion_mode=GRAPH_ENRICHMENT,
        emits_records=True,
        notes="League theme node enrichment/creation source.",
    ),

    SourceArtifactDeclaration(
        source_name="dim_teams_enhanced",
        artifact_kind=GraphArtifactKind.ENRICHMENT.value,
        target_label_or_rel="League",
        graph_contract_name="LeagueNode",
        inclusion_mode=GRAPH_ENRICHMENT,
        emits_records=True,
        notes="League reference resolution may enrich team-adjacent league metrics.",
    ),
)

# Explicit non-emitting declarations

NON_EMITTING_DECLARATIONS: tuple[SourceArtifactDeclaration, ...] = (
    SourceArtifactDeclaration(
        source_name="fct_user_notification_stats",
        artifact_kind=NON_EMITTING_ARTIFACT_KIND,
        target_label_or_rel="",
        graph_contract_name="",
        inclusion_mode=FEATURE_SOURCE,
        emits_records=False,
        notes="Notification feature view input only.",
    ),
    SourceArtifactDeclaration(
        source_name="fct_user_sessions",
        artifact_kind=NON_EMITTING_ARTIFACT_KIND,
        target_label_or_rel="",
        graph_contract_name="",
        inclusion_mode=FEATURE_SOURCE,
        emits_records=False,
        notes="Behavior model feature source only.",
    ),
    SourceArtifactDeclaration(
        source_name="fct_team_daily_growth",
        artifact_kind=NON_EMITTING_ARTIFACT_KIND,
        target_label_or_rel="",
        graph_contract_name="",
        inclusion_mode=FEATURE_SOURCE,
        emits_records=False,
        notes="Team analytics feature source only.",
    ),
    SourceArtifactDeclaration(
        source_name="fct_heatmap_events",
        artifact_kind=NON_EMITTING_ARTIFACT_KIND,
        target_label_or_rel="",
        graph_contract_name="",
        inclusion_mode=FEATURE_SOURCE,
        emits_records=False,
        notes="High-volume telemetry feature source only.",
    ),
    SourceArtifactDeclaration(
        source_name="fct_notification_content_daily",
        artifact_kind=NON_EMITTING_ARTIFACT_KIND,
        target_label_or_rel="",
        graph_contract_name="",
        inclusion_mode=FEATURE_SOURCE,
        emits_records=False,
        notes="Notification aggregate analytics only.",
    ),
    SourceArtifactDeclaration(
        source_name="fct_retention_cohorts",
        artifact_kind=NON_EMITTING_ARTIFACT_KIND,
        target_label_or_rel="",
        graph_contract_name="",
        inclusion_mode=SERVING_ONLY,
        emits_records=False,
        notes="Serving-only cohort retention dashboard source.",
    ),
    SourceArtifactDeclaration(
        source_name="fct_daily_metrics",
        artifact_kind=NON_EMITTING_ARTIFACT_KIND,
        target_label_or_rel="",
        graph_contract_name="",
        inclusion_mode=SERVING_ONLY,
        emits_records=False,
        notes="Operational dashboard metrics only.",
    ),
    SourceArtifactDeclaration(
        source_name="fct_content_engagement_daily",
        artifact_kind=NON_EMITTING_ARTIFACT_KIND,
        target_label_or_rel="",
        graph_contract_name="",
        inclusion_mode=SERVING_ONLY,
        emits_records=False,
        notes="Serving-only engagement aggregates.",
    ),
    
)

SOURCE_ARTIFACT_DECLARATIONS: tuple[SourceArtifactDeclaration, ...] = (
    CORE_NODE_DECLARATIONS
    + RELATIONSHIP_DECLARATIONS
    + ENRICHMENT_DECLARATIONS
    + NON_EMITTING_DECLARATIONS
)

_DECLARATIONS_BY_SOURCE: dict[str, list[SourceArtifactDeclaration]] = {}
for _declaration in SOURCE_ARTIFACT_DECLARATIONS:
    _DECLARATIONS_BY_SOURCE.setdefault(_declaration.source_name, []).append(_declaration)


def get_source_artifacts(source_name: str) -> list[SourceArtifactDeclaration]:
    """
    Return all artifact declarations for a given source.

    Args:
        source_name: Logical source/table name.

    Returns:
        List of declarations in registration order.
    """
    return list(_DECLARATIONS_BY_SOURCE.get(source_name, []))


def source_emits_graph_records(source_name: str) -> bool:
    """
    Return True if the source emits any graph records.

    Args:
        source_name: Logical source/table name.

    Returns:
        True if at least one declaration for the source has emits_records=True.
    """
    return any(decl.emits_records for decl in _DECLARATIONS_BY_SOURCE.get(source_name, []))


def get_graph_targets_for_source(source_name: str) -> list[str]:
    """
    Return graph labels / relationship types targeted by a source.

    Non-emitting declarations are excluded.

    Args:
        source_name: Logical source/table name.

    Returns:
        Ordered list of target labels / relationship types.
    """
    return [
        decl.target_label_or_rel
        for decl in _DECLARATIONS_BY_SOURCE.get(source_name, [])
        if decl.emits_records and decl.target_label_or_rel
    ]


def get_contract_names_for_source(source_name: str) -> list[str]:
    """
    Return graph contract names targeted by a source.

    Non-emitting declarations are excluded.

    Args:
        source_name: Logical source/table name.

    Returns:
        Ordered list of graph contract names.
    """
    return [
        decl.graph_contract_name
        for decl in _DECLARATIONS_BY_SOURCE.get(source_name, [])
        if decl.emits_records and decl.graph_contract_name
    ]


def validate_source_artifact_declarations() -> list[str]:
    """
    Validate all source artifact declarations.

    Checks:
    - source exists in source inventory registry when introspection is possible
    - inclusion_mode is valid
    - artifact_kind is valid
    - graph-emitting sources declare valid target labels / relationship types
    - non-emitting sources do not declare graph targets or contracts
    - graph-core / enrichment sources are coherent with emits_records
    - no source/target/contract duplicate declaration exists

    Returns:
        Flat list of validation error strings. Empty list means valid.
    """
    errors: list[str] = []
    registered_sources = _get_registered_source_names()

    seen_keys: set[tuple[str, str, str]] = set()
    valid_artifact_kinds = {
        GraphArtifactKind.NODE.value,
        GraphArtifactKind.RELATIONSHIP.value,
        GraphArtifactKind.ENRICHMENT.value,
        NON_EMITTING_ARTIFACT_KIND,
    }

    for idx, declaration in enumerate(SOURCE_ARTIFACT_DECLARATIONS):
        prefix = (
            f"SOURCE_ARTIFACT_DECLARATIONS[{idx}] "
            f"(source={declaration.source_name!r}, "
            f"target={declaration.target_label_or_rel!r})"
        )

        if not declaration.source_name or not declaration.source_name.strip():
            errors.append(f"{prefix}: source_name cannot be empty")

        if declaration.artifact_kind not in valid_artifact_kinds:
            errors.append(
                f"{prefix}: artifact_kind '{declaration.artifact_kind}' "
                f"must be one of {sorted(valid_artifact_kinds)}"
            )

        if declaration.inclusion_mode not in SOURCE_INCLUSION_CATEGORIES:
            errors.append(
                f"{prefix}: inclusion_mode '{declaration.inclusion_mode}' "
                f"is not in SOURCE_INCLUSION_CATEGORIES"
            )

        if registered_sources is not None and declaration.source_name not in registered_sources:
            errors.append(
                f"{prefix}: source_name '{declaration.source_name}' "
                f"is not registered in source inventory registry"
            )

        duplicate_key = (
            declaration.source_name,
            declaration.target_label_or_rel,
            declaration.graph_contract_name,
        )
        if duplicate_key in seen_keys:
            errors.append(
                f"{prefix}: duplicate source/target/contract declaration detected"
            )
        seen_keys.add(duplicate_key)

        if declaration.emits_records:
            if declaration.artifact_kind == NON_EMITTING_ARTIFACT_KIND:
                errors.append(
                    f"{prefix}: emits_records=True is inconsistent with artifact_kind='none'"
                )

            if not declaration.target_label_or_rel or not declaration.target_label_or_rel.strip():
                errors.append(
                    f"{prefix}: graph-emitting declaration must define target_label_or_rel"
                )

            if not declaration.graph_contract_name or not declaration.graph_contract_name.strip():
                errors.append(
                    f"{prefix}: graph-emitting declaration must define graph_contract_name"
                )

            if declaration.artifact_kind in {
                GraphArtifactKind.NODE.value,
                GraphArtifactKind.ENRICHMENT.value,
            }:
                if declaration.target_label_or_rel not in GRAPH_NODE_LABELS:
                    errors.append(
                        f"{prefix}: target label '{declaration.target_label_or_rel}' "
                        f"is not registered in GRAPH_NODE_LABELS"
                    )

            if declaration.artifact_kind == GraphArtifactKind.RELATIONSHIP.value:
                if declaration.target_label_or_rel not in GRAPH_RELATIONSHIP_TYPES:
                    errors.append(
                        f"{prefix}: relationship type '{declaration.target_label_or_rel}' "
                        f"is not registered in GRAPH_RELATIONSHIP_TYPES"
                    )

            if declaration.inclusion_mode in {FEATURE_SOURCE, SERVING_ONLY}:
                errors.append(
                    f"{prefix}: inclusion_mode '{declaration.inclusion_mode}' "
                    f"should not emit graph records"
                )

        else:
            if declaration.target_label_or_rel.strip():
                errors.append(
                    f"{prefix}: non-emitting declaration must not define target_label_or_rel"
                )
            if declaration.graph_contract_name.strip():
                errors.append(
                    f"{prefix}: non-emitting declaration must not define graph_contract_name"
                )
            if declaration.artifact_kind != NON_EMITTING_ARTIFACT_KIND:
                errors.append(
                    f"{prefix}: non-emitting declaration should use artifact_kind='none'"
                )
            if declaration.inclusion_mode not in {FEATURE_SOURCE, SERVING_ONLY}:
                errors.append(
                    f"{prefix}: non-emitting declaration should usually be "
                    f"FEATURE_SOURCE or SERVING_ONLY, got '{declaration.inclusion_mode}'"
                )

    return errors


def _get_registered_source_names() -> set[str] | None:
    """
    Best-effort introspection of source inventory registry source names.

    Returns:
        Set of registered source names when a compatible source inventory
        registry shape is available, otherwise None.

    This function is intentionally defensive because source inventory registry
    implementations may evolve independently of the mapping layer.
    """
    try:
        from app.source_inventory import registry as source_registry  # type: ignore
    except Exception:
        return None

    candidate_names = (
        "SOURCE_REGISTRY",
        "SOURCE_REGISTRATIONS",
        "SOURCE_DEFINITIONS",
        "REGISTERED_SOURCES",
        "ALL_SOURCES",
    )

    for attribute_name in candidate_names:
        if not hasattr(source_registry, attribute_name):
            continue

        value: Any = getattr(source_registry, attribute_name)

        source_names = _extract_source_names(value)
        if source_names:
            return source_names

    return None


def _extract_source_names(value: Any) -> set[str]:
    """
    Extract source names from a registry-like runtime object.

    Supported shapes:
    - dict[str, Any]
    - iterable[str]
    - iterable[object with .source_name]
    - iterable[dict with 'source_name']
    """
    if isinstance(value, dict):
        names = {str(key).strip() for key in value.keys() if str(key).strip()}
        if names:
            return names

        extracted: set[str] = set()
        for item in value.values():
            name = _source_name_from_item(item)
            if name:
                extracted.add(name)
        return extracted

    if isinstance(value, (list, tuple, set, frozenset)):
        extracted = set()
        for item in value:
            name = _source_name_from_item(item)
            if name:
                extracted.add(name)
        return extracted

    return set()


def _source_name_from_item(item: Any) -> str | None:
    """
    Best-effort extraction of source_name from one registry item.
    """
    if isinstance(item, str):
        stripped = item.strip()
        return stripped or None

    if isinstance(item, dict):
        raw = item.get("source_name")
        if raw is None:
            return None
        stripped = str(raw).strip()
        return stripped or None

    raw = getattr(item, "source_name", None)
    if raw is None:
        return None

    stripped = str(raw).strip()
    return stripped or None