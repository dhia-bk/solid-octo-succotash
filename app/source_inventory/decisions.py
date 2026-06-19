"""
Inclusion decision registry for Project Pulse Knowledge Graph source inventory.

This file documents the explicit rationale for every source table's inclusion
mode assignment. It is documentation-as-code: structured, versioned, and
queryable.

Design rules:
- This file defines rationale. It does not enforce rules (that is
  inclusion_rules.py) or store live state (that is app/db/source_inventory.py).
- Every table in the DWH schema must have exactly one InclusionDecision entry.
- If a table's inclusion mode changes, the decision entry must be updated with
  the reason for the change and a new decided_at date.
- decided_by should reflect the review process that approved the decision,
  not an individual's name.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.exceptions import SourceInventoryError
from app.core.logging import get_logger

logger = get_logger(__name__)

# ============================================================================
# Decision record dataclass
# ============================================================================


@dataclass(frozen=True)
class InclusionDecision:
    """
    Structured rationale for a source table's inclusion mode assignment.

    Attributes:
        source_name: Canonical warehouse table name.
        inclusion_mode: The assigned inclusion mode constant value.
        decision_reason: One or two sentences explaining why this mode was
            chosen over alternatives. Should be specific enough that a new
            team member understands the trade-off without asking.
        entity_impact: What graph nodes or relationships this source creates
            or enriches, or an explicit statement of why it feeds none.
        decided_by: The review process or role that approved this decision.
        decided_at: ISO date (YYYY-MM-DD) of the decision.
    """

    source_name: str
    inclusion_mode: str
    decision_reason: str
    entity_impact: str
    decided_by: str
    decided_at: str


# Decision registry — all 65 tables

_DECIDED_BY = "dhia"
_DECIDED_AT = "2026-06-25"

INCLUSION_DECISIONS: dict[str, InclusionDecision] = {

    # Identity

    "dim_users": InclusionDecision(
        source_name="dim_users",
        inclusion_mode="graph_core",
        decision_reason=(
            "dim_users is the primary identity node for the platform. Every "
            "user-centric edge in the graph — predictions, posts, memberships, "
            "duels, subscriptions — originates from a User node backed by this "
            "table. Excluding or downgrading it is not possible without losing "
            "the entire relational structure of the graph."
        ),
        entity_impact="Creates and owns the User node. All User-originating edges depend on this source.",
        decided_by=_DECIDED_BY,
        decided_at=_DECIDED_AT,
    ),

    "dim_avatars": InclusionDecision(
        source_name="dim_avatars",
        inclusion_mode="graph_core",
        decision_reason=(
            "Avatars are a first-class identity signal — they reveal user "
            "self-expression preferences and adoption patterns across the "
            "platform. The Avatar node is needed to model the EQUIPPED "
            "relationship (User → Avatar) and to support persona clustering "
            "by visual identity group."
        ),
        entity_impact="Creates Avatar nodes. Feeds EQUIPPED relationship (User → Avatar).",
        decided_by=_DECIDED_BY,
        decided_at=_DECIDED_AT,
    ),

    "dim_badges": InclusionDecision(
        source_name="dim_badges",
        inclusion_mode="graph_core",
        decision_reason=(
            "Badges represent achievement categories referenced by "
            "fct_awards_and_achievements. The Badge node is required as the "
            "target of the AWARDED relationship and as a stable catalog for "
            "badge-level analytics."
        ),
        entity_impact="Creates Badge nodes. Feeds AWARDED relationship (User → Badge).",
        decided_by=_DECIDED_BY,
        decided_at=_DECIDED_AT,
    ),

    "app_users": InclusionDecision(
        source_name="app_users",
        inclusion_mode="graph_enrichment",
        decision_reason=(
            "app_users is an auth bridge table that holds credential and login "
            "provider metadata for platform users. It enriches existing User "
            "nodes with auth_provider information but is not the canonical user "
            "identity source — dim_users holds that role. The password field "
            "must be dropped by the transformer and must never reach the graph."
        ),
        entity_impact=(
            "Enriches User nodes with auth provider and seeding metadata. "
            "Does not create new nodes or relationships."
        ),
        decided_by=_DECIDED_BY,
        decided_at=_DECIDED_AT,
    ),

    # Sports core

    "dim_teams": InclusionDecision(
        source_name="dim_teams",
        inclusion_mode="graph_core",
        decision_reason=(
            "Teams are a foundational sports entity referenced by fixtures, "
            "predictions, affinity scores, and fan behavior. The Team node is "
            "required as the anchor for FAVORS, HAS_AFFINITY, HOME_TEAM, and "
            "AWAY_TEAM relationships. dim_teams provides the canonical team "
            "catalog and is a static dimension with infrequent changes."
        ),
        entity_impact="Creates Team nodes. Feeds FAVORS, HAS_AFFINITY, HOME_TEAM, AWAY_TEAM relationships.",
        decided_by=_DECIDED_BY,
        decided_at=_DECIDED_AT,
    ),

    "dim_teams_enhanced": InclusionDecision(
        source_name="dim_teams_enhanced",
        inclusion_mode="graph_enrichment",
        decision_reason=(
            "dim_teams_enhanced adds computed fan analytics (fan count, "
            "engagement score, growth rate, fan retention) to existing Team "
            "nodes. These are aggregate properties, not a new entity. Creating "
            "a separate node for this data would misrepresent the ontology — "
            "it is still the same Team with richer observable properties."
        ),
        entity_impact=(
            "Enriches Team nodes with fan analytics computed properties. "
            "Does not create new nodes or relationships."
        ),
        decided_by=_DECIDED_BY,
        decided_at=_DECIDED_AT,
    ),

    "dim_leagues": InclusionDecision(
        source_name="dim_leagues",
        inclusion_mode="graph_core",
        decision_reason=(
            "Leagues are the competition structure that links teams and fixtures. "
            "The League node is required as the target of IN_LEAGUE (Match → League) "
            "and PLAYS_IN (Team → League) relationships, and as a grouping axis "
            "for tribe-level analytics."
        ),
        entity_impact="Creates League nodes. Feeds IN_LEAGUE and PLAYS_IN relationships.",
        decided_by=_DECIDED_BY,
        decided_at=_DECIDED_AT,
    ),

    "dim_fixtures": InclusionDecision(
        source_name="dim_fixtures",
        inclusion_mode="graph_core",
        decision_reason=(
            "Fixtures (matches) are the primary event entity around which user "
            "predictions, discussions, and duels are organized. The Match node "
            "is required as the target of PREDICTED, HOME_TEAM, AWAY_TEAM, "
            "IN_LEAGUE, ABOUT, and HAS_FIXTURE relationships."
        ),
        entity_impact=(
            "Creates Match nodes. Feeds PREDICTED, HOME_TEAM, AWAY_TEAM, "
            "IN_LEAGUE, ABOUT, and HAS_FIXTURE relationships."
        ),
        decided_by=_DECIDED_BY,
        decided_at=_DECIDED_AT,
    ),

    # Social

    "dim_private_leagues": InclusionDecision(
        source_name="dim_private_leagues",
        inclusion_mode="graph_core",
        decision_reason=(
            "Private leagues are the core social grouping mechanism of the "
            "platform. They are the context in which most user predictions and "
            "community interactions occur. The PrivateLeague node is required "
            "as the target of MEMBER_OF relationships and as the owner entity "
            "for league-level tribe detection."
        ),
        entity_impact="Creates PrivateLeague nodes. Feeds MEMBER_OF relationship (User → PrivateLeague).",
        decided_by=_DECIDED_BY,
        decided_at=_DECIDED_AT,
    ),

    "dim_private_league_members": InclusionDecision(
        source_name="dim_private_league_members",
        inclusion_mode="graph_core",
        decision_reason=(
            "Membership edges are the primary structural signal for community "
            "detection. The co-membership pattern between users in private "
            "leagues is the main input to the Leiden algorithm. Without this "
            "table, tribe detection is not possible."
        ),
        entity_impact=(
            "Feeds MEMBER_OF relationship (User → PrivateLeague) with role, "
            "join date, and activity metadata as edge properties."
        ),
        decided_by=_DECIDED_BY,
        decided_at=_DECIDED_AT,
    ),

    "dim_private_league_themes": InclusionDecision(
        source_name="dim_private_league_themes",
        inclusion_mode="graph_enrichment",
        decision_reason=(
            "League themes carry visual customization data (colors, banners) "
            "associated with a PrivateLeague. They describe presentation "
            "attributes of the league, not a distinct social entity. "
            "A LeagueTheme node is modeled as an enrichment to support "
            "HAS_THEME relationship queries without polluting the core "
            "PrivateLeague node with display properties."
        ),
        entity_impact=(
            "Creates LeagueTheme nodes. Feeds HAS_THEME relationship "
            "(PrivateLeague → LeagueTheme)."
        ),
        decided_by=_DECIDED_BY,
        decided_at=_DECIDED_AT,
    ),

    "dim_posts": InclusionDecision(
        source_name="dim_posts",
        inclusion_mode="graph_core",
        decision_reason=(
            "Posts are user-generated content that carries topic and sentiment "
            "signals and links users to their expressed opinions. The Post node "
            "is required for POSTED (User → Post), COMMENTED (User → Comment "
            "on Post), and HAS_TAG (Post → Tag) relationships."
        ),
        entity_impact="Creates Post nodes. Feeds POSTED and HAS_TAG relationships.",
        decided_by=_DECIDED_BY,
        decided_at=_DECIDED_AT,
    ),

    "dim_comments": InclusionDecision(
        source_name="dim_comments",
        inclusion_mode="graph_core",
        decision_reason=(
            "Comments are social engagement signals that reveal which users "
            "interact around the same content. They are needed for COMMENTED "
            "(User → Comment) and REPLIES_TO (Comment → Comment) relationships "
            "and for thread-level sentiment analysis."
        ),
        entity_impact="Creates Comment nodes. Feeds COMMENTED and REPLIES_TO relationships.",
        decided_by=_DECIDED_BY,
        decided_at=_DECIDED_AT,
    ),

    "dim_discussions": InclusionDecision(
        source_name="dim_discussions",
        inclusion_mode="graph_core",
        decision_reason=(
            "Discussions are fixture-linked conversation threads that capture "
            "which users engage around the same match event. The Discussion node "
            "is required for the JOINED_DISCUSSION relationship and for linking "
            "discussion events to their parent fixture."
        ),
        entity_impact="Creates Discussion nodes. Feeds JOINED_DISCUSSION relationship (User → Discussion).",
        decided_by=_DECIDED_BY,
        decided_at=_DECIDED_AT,
    ),

    "dim_prediction_discussions": InclusionDecision(
        source_name="dim_prediction_discussions",
        inclusion_mode="graph_core",
        decision_reason=(
            "Prediction discussions are a specialised discussion type linked to "
            "specific predictions rather than fixtures directly. They are "
            "modeled as a distinct node type to preserve the ontological "
            "distinction between fixture discussions and prediction-level "
            "commentary."
        ),
        entity_impact=(
            "Creates PredictionDiscussion nodes. Feeds ABOUT relationship "
            "(PredictionDiscussion → Match)."
        ),
        decided_by=_DECIDED_BY,
        decided_at=_DECIDED_AT,
    ),

    "fct_discussion_events": InclusionDecision(
        source_name="fct_discussion_events",
        inclusion_mode="graph_core",
        decision_reason=(
            "Discussion events capture the moment a user participates in a "
            "fixture discussion, including the event type and content preview. "
            "This is the primary source for the JOINED_DISCUSSION edge "
            "properties and provides richer temporal context than the discussion "
            "dimension alone."
        ),
        entity_impact=(
            "Feeds JOINED_DISCUSSION relationship (User → Discussion) with "
            "event type and timestamp properties."
        ),
        decided_by=_DECIDED_BY,
        decided_at=_DECIDED_AT,
    ),

    "dim_chat_conversations_mysql": InclusionDecision(
        source_name="dim_chat_conversations_mysql",
        inclusion_mode="graph_core",
        decision_reason=(
            "Group and direct chat conversations represent a distinct social "
            "communication channel separate from post/comment interactions. "
            "The Conversation node links private league chat groups to their "
            "member users and enables communication-pattern analysis."
        ),
        entity_impact="Creates Conversation nodes. Feeds DIRECT_MESSAGE relationship context.",
        decided_by=_DECIDED_BY,
        decided_at=_DECIDED_AT,
    ),

    "dim_chat_direct_pairs": InclusionDecision(
        source_name="dim_chat_direct_pairs",
        inclusion_mode="graph_core",
        decision_reason=(
            "Direct message pairs capture the existence of a private 1-to-1 "
            "communication channel between two users. The DirectPair node "
            "provides a stable, deduplicated representation of this link "
            "regardless of message volume, enabling social proximity analysis."
        ),
        entity_impact=(
            "Creates DirectPair nodes. Feeds DIRECT_MESSAGE relationship "
            "(User → DirectPair)."
        ),
        decided_by=_DECIDED_BY,
        decided_at=_DECIDED_AT,
    ),

    # Intelligence

    "fct_user_behavior": InclusionDecision(
        source_name="fct_user_behavior",
        inclusion_mode="graph_enrichment",
        decision_reason=(
            "fct_user_behavior provides the PCM stage and behaviour label "
            "computed by the behaviour model. These are enrichment inputs to "
            "PersonaState construction, not the canonical PersonaState node "
            "itself. The PersonaState node is built by the temporal pipeline "
            "using these signals as one of several inputs."
        ),
        entity_impact=(
            "Enriches PersonaState construction with pcm_stage, behaviour_label, "
            "birfing_coefficient, and frustration_bias signals."
        ),
        decided_by=_DECIDED_BY,
        decided_at=_DECIDED_AT,
    ),

    "fct_topics": InclusionDecision(
        source_name="fct_topics",
        inclusion_mode="graph_core",
        decision_reason=(
            "Topics are ML-derived labels that classify what content items and "
            "users are talking about. The Topic node is required to model "
            "DISCUSSED (User → Topic) relationships and to support topic-based "
            "tribe cohesion analysis."
        ),
        entity_impact="Creates Topic nodes. Feeds DISCUSSED relationship (User → Topic).",
        decided_by=_DECIDED_BY,
        decided_at=_DECIDED_AT,
    ),

    "fct_sentiment": InclusionDecision(
        source_name="fct_sentiment",
        inclusion_mode="graph_core",
        decision_reason=(
            "Sentiment scores are ML-derived signals that capture user emotional "
            "tone per content item. The Sentiment node is required to model "
            "EXPRESSED (User → Sentiment) relationships and to support "
            "sentiment-aware persona clustering."
        ),
        entity_impact="Creates Sentiment nodes. Feeds EXPRESSED relationship (User → Sentiment).",
        decided_by=_DECIDED_BY,
        decided_at=_DECIDED_AT,
    ),

    "fct_team_affinity": InclusionDecision(
        source_name="fct_team_affinity",
        inclusion_mode="graph_core",
        decision_reason=(
            "Team affinity scores encode the strength of a user's attachment to "
            "a team, computed from prediction history and content engagement. "
            "This is a computed relationship property that warrants a dedicated "
            "HAS_AFFINITY edge with rich metrics rather than a scalar property "
            "on the User node."
        ),
        entity_impact=(
            "Feeds HAS_AFFINITY relationship (User → Team) with affinity type, "
            "prediction accuracy, engagement frequency, and is_active_fan properties."
        ),
        decided_by=_DECIDED_BY,
        decided_at=_DECIDED_AT,
    ),

    "fct_user_activities": InclusionDecision(
        source_name="fct_user_activities",
        inclusion_mode="graph_enrichment",
        decision_reason=(
            "User activity events are fine-grained behavioral signals (reactions, "
            "invites, content interactions) used to compute activity weights on "
            "User nodes. They are enrichment inputs rather than independent "
            "graph entities — modeling each activity as a node would produce "
            "an impractically dense graph."
        ),
        entity_impact=(
            "Enriches User nodes with activity weight signals. "
            "Does not create new nodes or relationships."
        ),
        decided_by=_DECIDED_BY,
        decided_at=_DECIDED_AT,
    ),

    "fct_user_sessions": InclusionDecision(
        source_name="fct_user_sessions",
        inclusion_mode="feature_source",
        decision_reason=(
            "Session aggregates capture per-user browsing behavior (duration, "
            "page views, landing/exit pages) that feeds the behaviour model "
            "feature pipeline. Sessions are transient, user-anchored records "
            "with no stable cross-user relationship value, making them "
            "unsuitable as graph nodes."
        ),
        entity_impact=(
            "No graph entity mapping. Feeds ML feature computation pipelines "
            "for behaviour model inputs."
        ),
        decided_by=_DECIDED_BY,
        decided_at=_DECIDED_AT,
    ),

    "fct_user_rating_history": InclusionDecision(
        source_name="fct_user_rating_history",
        inclusion_mode="graph_core",
        decision_reason=(
            "Rating history captures the ELO-style duel rating change events "
            "per user over time. Modeling each change as a RatingSnapshot node "
            "enables temporal analysis of user skill progression and supports "
            "HAS_RATING relationship queries for trend detection."
        ),
        entity_impact=(
            "Creates RatingSnapshot nodes. Feeds HAS_RATING relationship "
            "(User → RatingSnapshot)."
        ),
        decided_by=_DECIDED_BY,
        decided_at=_DECIDED_AT,
    ),

    # Competition

    "fct_predictions": InclusionDecision(
        source_name="fct_predictions",
        inclusion_mode="graph_core",
        decision_reason=(
            "Predictions are the primary engagement event on the platform and "
            "the main source of the PREDICTED relationship (User → Match). "
            "They carry prediction context, accuracy signals, and point awards "
            "that are core inputs to tribe detection and persona modeling."
        ),
        entity_impact=(
            "Feeds PREDICTED relationship (User → Match) with prediction "
            "outcome, accuracy, points, and context properties."
        ),
        decided_by=_DECIDED_BY,
        decided_at=_DECIDED_AT,
    ),

    "fct_prediction_duels": InclusionDecision(
        source_name="fct_prediction_duels",
        inclusion_mode="graph_core",
        decision_reason=(
            "Duels are competitive prediction challenges between two users that "
            "carry coin stakes and rating implications. The Duel node captures "
            "this bilateral interaction as a named entity, enabling analysis of "
            "competitive social graphs and duel outcome patterns."
        ),
        entity_impact=(
            "Creates Duel nodes. Feeds CHALLENGED relationship "
            "(User → Duel) for sender and receiver participants."
        ),
        decided_by=_DECIDED_BY,
        decided_at=_DECIDED_AT,
    ),

    "dim_super6_rounds": InclusionDecision(
        source_name="dim_super6_rounds",
        inclusion_mode="graph_core",
        decision_reason=(
            "Super6 rounds are a structured competition format where users "
            "predict outcomes across six fixtures. The Super6Round node is "
            "required as the target of HAS_FIXTURE and PARTICIPATED_IN "
            "relationships."
        ),
        entity_impact=(
            "Creates Super6Round nodes. Feeds HAS_FIXTURE relationship "
            "(Super6Round → Match) and PARTICIPATED_IN relationship "
            "(User → Super6Round)."
        ),
        decided_by=_DECIDED_BY,
        decided_at=_DECIDED_AT,
    ),

    "dim_super6_round_fixtures": InclusionDecision(
        source_name="dim_super6_round_fixtures",
        inclusion_mode="graph_core",
        decision_reason=(
            "This junction table links each Super6 round to its constituent "
            "fixtures. It is required to build HAS_FIXTURE relationships and "
            "cannot be inferred from the round or fixture tables alone."
        ),
        entity_impact=(
            "Feeds HAS_FIXTURE relationship (Super6Round → Match). "
            "Does not create new node types."
        ),
        decided_by=_DECIDED_BY,
        decided_at=_DECIDED_AT,
    ),

    "fct_super6_participants": InclusionDecision(
        source_name="fct_super6_participants",
        inclusion_mode="graph_core",
        decision_reason=(
            "Super6 participation facts capture per-user round performance "
            "(points, correct scores, winner status). These properties make "
            "the PARTICIPATED_IN relationship informative beyond a simple "
            "presence edge."
        ),
        entity_impact=(
            "Feeds PARTICIPATED_IN relationship (User → Super6Round) with "
            "points, correct scores, and winner flag properties."
        ),
        decided_by=_DECIDED_BY,
        decided_at=_DECIDED_AT,
    ),

    "dim_lms_competitions": InclusionDecision(
        source_name="dim_lms_competitions",
        inclusion_mode="graph_core",
        decision_reason=(
            "Last Man Standing competitions are private league-based elimination "
            "contests with coin prize pools. The LMSCompetition node models this "
            "as a distinct competition entity, enabling analysis of elimination "
            "patterns and prize distribution across league communities."
        ),
        entity_impact=(
            "Creates LMSCompetition nodes. Feeds PARTICIPATED_IN relationship "
            "(User → LMSCompetition)."
        ),
        decided_by=_DECIDED_BY,
        decided_at=_DECIDED_AT,
    ),

    # AI / communication

    "dim_chatbot_conversations": InclusionDecision(
        source_name="dim_chatbot_conversations",
        inclusion_mode="graph_core",
        decision_reason=(
            "AI chatbot conversations represent a distinct user-AI interaction "
            "channel with measurable engagement signals (duration, message count, "
            "tool usage). The ChatbotConversation node enables analysis of which "
            "user segments use AI features most and how that correlates with "
            "prediction behavior."
        ),
        entity_impact=(
            "Creates ChatbotConversation nodes. Feeds TALKED_TO relationship "
            "(User → ChatbotConversation)."
        ),
        decided_by=_DECIDED_BY,
        decided_at=_DECIDED_AT,
    ),

    "fct_chatbot_messages": InclusionDecision(
        source_name="fct_chatbot_messages",
        inclusion_mode="graph_core",
        decision_reason=(
            "Individual chatbot messages carry token usage, model name, and "
            "message ordering metadata that is needed to analyze conversation "
            "depth and AI usage cost per user segment."
        ),
        entity_impact=(
            "Creates ChatbotMessage nodes. Feeds HAS_MESSAGE relationship "
            "(ChatbotConversation → ChatbotMessage)."
        ),
        decided_by=_DECIDED_BY,
        decided_at=_DECIDED_AT,
    ),

    "fct_chatbot_tool_calls": InclusionDecision(
        source_name="fct_chatbot_tool_calls",
        inclusion_mode="graph_core",
        decision_reason=(
            "Tool calls track which AI capabilities (tools) users trigger through "
            "the chatbot. Modeling them as ToolCall nodes enables analysis of "
            "feature adoption patterns per user segment and supports USED_TOOL "
            "relationship queries."
        ),
        entity_impact=(
            "Creates ToolCall nodes. Feeds USED_TOOL relationship "
            "(ChatbotMessage → ToolCall)."
        ),
        decided_by=_DECIDED_BY,
        decided_at=_DECIDED_AT,
    ),

    "dim_ai_articles": InclusionDecision(
        source_name="dim_ai_articles",
        inclusion_mode="graph_core",
        decision_reason=(
            "AI-generated articles are content entities published to users and "
            "linked to match events. The AIArticle node enables analysis of "
            "content generation patterns and user engagement with AI content "
            "versus human-authored news."
        ),
        entity_impact=(
            "Creates AIArticle nodes. Feeds GENERATED_FOR relationship "
            "(AIArticle → Match) and HAS_TAG relationship (AIArticle → Tag)."
        ),
        decided_by=_DECIDED_BY,
        decided_at=_DECIDED_AT,
    ),

    "dim_news": InclusionDecision(
        source_name="dim_news",
        inclusion_mode="graph_core",
        decision_reason=(
            "News items are editorial content entities that users read and "
            "react to. The News node enables tag-based content recommendation "
            "analysis and supports HAS_TAG relationship modeling alongside "
            "AI-generated articles."
        ),
        entity_impact=(
            "Creates News nodes. Feeds HAS_TAG relationship (News → Tag)."
        ),
        decided_by=_DECIDED_BY,
        decided_at=_DECIDED_AT,
    ),

    # Economy

    "fct_coin_transactions": InclusionDecision(
        source_name="fct_coin_transactions",
        inclusion_mode="graph_core",
        decision_reason=(
            "Coin transactions are the primary economic activity log on the "
            "platform. The CoinTransaction node captures each earn/spend event "
            "with its type and balance impact, enabling economy-behavior "
            "correlation analysis through SPENT relationship patterns."
        ),
        entity_impact=(
            "Creates CoinTransaction nodes. Feeds SPENT relationship "
            "(User → CoinTransaction)."
        ),
        decided_by=_DECIDED_BY,
        decided_at=_DECIDED_AT,
    ),

    "dim_voucher_catalog": InclusionDecision(
        source_name="dim_voucher_catalog",
        inclusion_mode="graph_core",
        decision_reason=(
            "The voucher catalog defines the redeemable reward products "
            "available to users. The Voucher node is required as the target of "
            "PURCHASED relationships and for catalog-level engagement analysis."
        ),
        entity_impact=(
            "Creates Voucher nodes. Feeds PURCHASED relationship (User → Voucher)."
        ),
        decided_by=_DECIDED_BY,
        decided_at=_DECIDED_AT,
    ),

    "fct_voucher_purchases": InclusionDecision(
        source_name="fct_voucher_purchases",
        inclusion_mode="graph_core",
        decision_reason=(
            "Voucher purchases record the moment a user spends coins to acquire "
            "a voucher. The purchase event is the primary source of the "
            "PURCHASED relationship and carries redemption status that "
            "indicates follow-through behavior."
        ),
        entity_impact=(
            "Feeds PURCHASED relationship (User → Voucher) with coin cost, "
            "purchase date, and redemption status properties."
        ),
        decided_by=_DECIDED_BY,
        decided_at=_DECIDED_AT,
    ),

    "dim_partner_reward_catalog": InclusionDecision(
        source_name="dim_partner_reward_catalog",
        inclusion_mode="graph_core",
        decision_reason=(
            "Partner rewards are branded real-world rewards available through "
            "the coin economy. The PartnerReward node is required as the target "
            "of REDEEMED relationships and for partner-level redemption analysis."
        ),
        entity_impact=(
            "Creates PartnerReward nodes. Feeds REDEEMED relationship "
            "(User → PartnerReward)."
        ),
        decided_by=_DECIDED_BY,
        decided_at=_DECIDED_AT,
    ),

    "fct_partner_reward_inventory": InclusionDecision(
        source_name="fct_partner_reward_inventory",
        inclusion_mode="graph_enrichment",
        decision_reason=(
            "The inventory event table enriches PartnerReward nodes with "
            "stock levels and event-driven updates from the rewards pipeline. "
            "It does not introduce a new reward entity — it updates the stock "
            "and pricing state of rewards already created from the catalog."
        ),
        entity_impact=(
            "Enriches PartnerReward nodes with stock_total, discount_price, "
            "and expiration data. Does not create new nodes."
        ),
        decided_by=_DECIDED_BY,
        decided_at=_DECIDED_AT,
    ),

    "fct_partner_reward_redemptions": InclusionDecision(
        source_name="fct_partner_reward_redemptions",
        inclusion_mode="graph_core",
        decision_reason=(
            "Redemption events record the actual fulfilment of a partner reward "
            "for a user. This is the primary source of the REDEEMED relationship "
            "and carries quantity, transaction amount, and timing data that "
            "enriches the edge. The user_email field must be dropped by the "
            "transformer before any downstream processing."
        ),
        entity_impact=(
            "Feeds REDEEMED relationship (User → PartnerReward) with quantity, "
            "transaction amount, and redemption date properties."
        ),
        decided_by=_DECIDED_BY,
        decided_at=_DECIDED_AT,
    ),

    "dim_subscription_products": InclusionDecision(
        source_name="dim_subscription_products",
        inclusion_mode="graph_core",
        decision_reason=(
            "Subscription products define the tier catalog of paid features "
            "available on the platform. The SubscriptionProduct node is required "
            "as the target of SUBSCRIBED_TO relationships and for tier-level "
            "behavior segmentation analysis."
        ),
        entity_impact=(
            "Creates SubscriptionProduct nodes. Feeds SUBSCRIBED_TO relationship "
            "(User → SubscriptionProduct)."
        ),
        decided_by=_DECIDED_BY,
        decided_at=_DECIDED_AT,
    ),

    "fct_subscription_lifecycle": InclusionDecision(
        source_name="fct_subscription_lifecycle",
        inclusion_mode="graph_core",
        decision_reason=(
            "Subscription lifecycle events capture the full history of a user's "
            "subscription changes (new, renewal, churn, win-back). The edge "
            "properties (event type, amount paid, churn risk score) make this "
            "significantly more informative than a static subscription flag on "
            "the User node."
        ),
        entity_impact=(
            "Feeds SUBSCRIBED_TO relationship (User → SubscriptionProduct) with "
            "event type, amount paid, billing cycle, and churn risk properties."
        ),
        decided_by=_DECIDED_BY,
        decided_at=_DECIDED_AT,
    ),

    "fct_financials": InclusionDecision(
        source_name="fct_financials",
        inclusion_mode="graph_core",
        decision_reason=(
            "Financial events are the authoritative payment record on the "
            "platform, capturing revenue transactions with payment method and "
            "MRR impact. The FinancialEvent node enables payment-behavior "
            "correlation analysis at the user level."
        ),
        entity_impact=(
            "Creates FinancialEvent nodes linked to User nodes through the "
            "user_id field. No named relationship type defined yet — resolved "
            "in the financial transformer."
        ),
        decided_by=_DECIDED_BY,
        decided_at=_DECIDED_AT,
    ),

    "fct_awards_and_achievements": InclusionDecision(
        source_name="fct_awards_and_achievements",
        inclusion_mode="graph_core",
        decision_reason=(
            "Achievement events record the moment a user earns a badge, trophy, "
            "or reward. This table feeds both Achievement node creation (one per "
            "distinct award event) and the ACHIEVED relationship (User → "
            "Achievement), enabling gamification-behavior analysis."
        ),
        entity_impact=(
            "Creates Achievement nodes and feeds ACHIEVED relationship "
            "(User → Achievement) with earned_at and reward_amount properties."
        ),
        decided_by=_DECIDED_BY,
        decided_at=_DECIDED_AT,
    ),

    # Engagement

    "dim_fixture_polls_enhanced": InclusionDecision(
        source_name="dim_fixture_polls_enhanced",
        inclusion_mode="graph_core",
        decision_reason=(
            "Fixture polls are engagement units tied to specific matches that "
            "reveal user opinion on match outcomes. The Poll node links to "
            "fixtures and captures response distribution, enabling poll-type "
            "engagement analysis within tribe detection."
        ),
        entity_impact=(
            "Creates Poll nodes linked to Match nodes through fixture_id. "
            "Feeds HAS_TAG and poll response relationship patterns."
        ),
        decided_by=_DECIDED_BY,
        decided_at=_DECIDED_AT,
    ),

    "dim_questions": InclusionDecision(
        source_name="dim_questions",
        inclusion_mode="graph_core",
        decision_reason=(
            "Questions are interactive yes/no engagement units broadcast to "
            "users. The Question node is the canonical entity for question "
            "content, used as the target of user response relationship patterns."
        ),
        entity_impact=(
            "Creates Question nodes. Foundation for question response "
            "relationship modeling in the engagement pipeline."
        ),
        decided_by=_DECIDED_BY,
        decided_at=_DECIDED_AT,
    ),

    "dim_questions_enhanced": InclusionDecision(
        source_name="dim_questions_enhanced",
        inclusion_mode="graph_enrichment",
        decision_reason=(
            "dim_questions_enhanced adds engagement analytics (response counts, "
            "yes/no distribution, response timing) to existing Question nodes. "
            "These are aggregate metrics computed over response events, not a "
            "new entity. Merging them with the base Question node keeps the "
            "ontology clean."
        ),
        entity_impact=(
            "Enriches Question nodes with response analytics. "
            "Does not create new nodes or relationships."
        ),
        decided_by=_DECIDED_BY,
        decided_at=_DECIDED_AT,
    ),

    "dim_quizzes": InclusionDecision(
        source_name="dim_quizzes",
        inclusion_mode="graph_core",
        decision_reason=(
            "Quizzes are knowledge competition units that group quiz questions "
            "into a structured engagement format. The Quiz node is required as "
            "the container for QuizQuestion nodes and supports quiz-level "
            "engagement segmentation."
        ),
        entity_impact=(
            "Creates Quiz nodes. Feeds HAS_QUESTION relationship pattern "
            "(Quiz → QuizQuestion)."
        ),
        decided_by=_DECIDED_BY,
        decided_at=_DECIDED_AT,
    ),

    "dim_quiz_questions_enhanced": InclusionDecision(
        source_name="dim_quiz_questions_enhanced",
        inclusion_mode="graph_core",
        decision_reason=(
            "Quiz questions include performance analytics (accuracy rate, "
            "difficulty level, option distribution) that are intrinsic to the "
            "question entity, not derived at query time. Including these in the "
            "graph node avoids expensive joins in the serving layer."
        ),
        entity_impact=(
            "Creates QuizQuestion nodes with embedded analytics. Feeds the "
            "HAS_QUESTION relationship (Quiz → QuizQuestion)."
        ),
        decided_by=_DECIDED_BY,
        decided_at=_DECIDED_AT,
    ),

    "dim_tags": InclusionDecision(
        source_name="dim_tags",
        inclusion_mode="graph_core",
        decision_reason=(
            "Tags are the content taxonomy that links posts, news, and AI "
            "articles to team and league entities. The Tag node is required "
            "for HAS_TAG relationships and for topic-based content clustering "
            "in the recommendation layer."
        ),
        entity_impact=(
            "Creates Tag nodes. Feeds HAS_TAG relationship (Post → Tag, "
            "News → Tag, AIArticle → Tag)."
        ),
        decided_by=_DECIDED_BY,
        decided_at=_DECIDED_AT,
    ),

    "dim_notification_content": InclusionDecision(
        source_name="dim_notification_content",
        inclusion_mode="graph_core",
        decision_reason=(
            "Notification content represents deduplicated, normalized message "
            "templates sent to users. Modeling them as NotificationContent nodes "
            "allows the RECEIVED_NOTIFICATION relationship to reference a stable "
            "content entity rather than repeating raw message text on every edge."
        ),
        entity_impact=(
            "Creates NotificationContent nodes. Feeds RECEIVED_NOTIFICATION "
            "relationship (User → NotificationContent)."
        ),
        decided_by=_DECIDED_BY,
        decided_at=_DECIDED_AT,
    ),

    "dim_notification_preferences": InclusionDecision(
        source_name="dim_notification_preferences",
        inclusion_mode="graph_enrichment",
        decision_reason=(
            "Notification preferences carry consent signals and device "
            "registration metadata that enrich the User node's communication "
            "profile. They do not represent a distinct entity — they describe "
            "the notification relationship attributes of the user. The "
            "transformer must group by user_id before writing enrichment "
            "properties, as one user may have multiple category rows."
        ),
        entity_impact=(
            "Enriches User nodes with notification consent and device metadata. "
            "Does not create new nodes or relationships."
        ),
        decided_by=_DECIDED_BY,
        decided_at=_DECIDED_AT,
    ),

    "fct_notification_content_daily": InclusionDecision(
        source_name="fct_notification_content_daily",
        inclusion_mode="feature_source",
        decision_reason=(
            "Daily delivery aggregates per notification content item provide "
            "read rate and recipient count signals used by the notification "
            "scoring model to rank and personalize notification delivery. "
            "These are content-level aggregates, not per-user entity facts, "
            "making them unsuitable as graph nodes."
        ),
        entity_impact=(
            "No graph entity mapping. Feeds notification scoring model "
            "feature computation."
        ),
        decided_by=_DECIDED_BY,
        decided_at=_DECIDED_AT,
    ),

    "jct_notification_recipients": InclusionDecision(
        source_name="jct_notification_recipients",
        inclusion_mode="graph_core",
        decision_reason=(
            "The notification recipients junction table is the source of truth "
            "for which users received which notifications and whether they read "
            "them. The RECEIVED_NOTIFICATION relationship carries is_read and "
            "read_at properties that are essential for notification engagement "
            "analysis at the persona level."
        ),
        entity_impact=(
            "Feeds RECEIVED_NOTIFICATION relationship (User → NotificationContent) "
            "with sent_at, is_read, and read_at properties."
        ),
        decided_by=_DECIDED_BY,
        decided_at=_DECIDED_AT,
    ),

    "fct_user_notification_stats": InclusionDecision(
        source_name="fct_user_notification_stats",
        inclusion_mode="feature_source",
        decision_reason=(
            "Per-user notification engagement aggregates (read rate, consistency "
            "score, active days) are pre-computed rollups that feed the serving "
            "layer and notification feature views. They duplicate information "
            "derivable from jct_notification_recipients and are not needed "
            "directly in the graph — they are consumed by the notification "
            "feature pipeline after graph construction."
        ),
        entity_impact=(
            "No graph entity mapping. Feeds notification feature view "
            "computation in the serving layer."
        ),
        decided_by=_DECIDED_BY,
        decided_at=_DECIDED_AT,
    ),

    # Ops

    "fct_moderation_events": InclusionDecision(
        source_name="fct_moderation_events",
        inclusion_mode="graph_core",
        decision_reason=(
            "Moderation events record enforcement actions taken against users "
            "or content. The ModerationEvent node enables analysis of moderation "
            "patterns by user segment and supports the MODERATED relationship "
            "(User → ModerationEvent) for auditing trust and safety behavior."
        ),
        entity_impact=(
            "Creates ModerationEvent nodes. Feeds MODERATED relationship "
            "(User → ModerationEvent) for moderator-side actions."
        ),
        decided_by=_DECIDED_BY,
        decided_at=_DECIDED_AT,
    ),

    "fct_daily_metrics": InclusionDecision(
        source_name="fct_daily_metrics",
        inclusion_mode="serving_only",
        decision_reason=(
            "fct_daily_metrics contains platform-wide aggregate KPIs (DAU, MRR, "
            "churn rate, retention rates) computed at the platform level, not "
            "the entity level. There is no per-user or per-entity node to attach "
            "these metrics to — they are consumed directly by operational "
            "dashboards without graph intermediation."
        ),
        entity_impact=(
            "No graph entity mapping. Consumed by operational dashboards "
            "and the serving layer directly."
        ),
        decided_by=_DECIDED_BY,
        decided_at=_DECIDED_AT,
    ),

    "fct_content_engagement_daily": InclusionDecision(
        source_name="fct_content_engagement_daily",
        inclusion_mode="serving_only",
        decision_reason=(
            "Daily content engagement rollups (likes, comments, tag counts per "
            "content item per day) are pre-aggregated for dashboard consumption. "
            "The information they contain is derivable from the graph at query "
            "time, making a second graph representation redundant."
        ),
        entity_impact=(
            "No graph entity mapping. Feeds content engagement dashboards "
            "in the serving layer."
        ),
        decided_by=_DECIDED_BY,
        decided_at=_DECIDED_AT,
    ),

    "fct_heatmap_events": InclusionDecision(
        source_name="fct_heatmap_events",
        inclusion_mode="feature_source",
        decision_reason=(
            "Heatmap events are a raw UX interaction stream (clicks, scrolls, "
            "page coordinates) captured at high volume per session. This data "
            "is too granular and too high-volume to model in the graph. It is "
            "consumed by the behaviour model to compute engagement signals that "
            "feed into the graph indirectly via fct_user_behavior."
        ),
        entity_impact=(
            "No graph entity mapping. Feeds behaviour model feature computation "
            "upstream of fct_user_behavior."
        ),
        decided_by=_DECIDED_BY,
        decided_at=_DECIDED_AT,
    ),

    "fct_retention_cohorts": InclusionDecision(
        source_name="fct_retention_cohorts",
        inclusion_mode="serving_only",
        decision_reason=(
            "Retention cohort data aggregates groups of users by signup week "
            "and tracks their activity over time. There is no per-user entity "
            "mapping — cohorts are statistical groupings, not graph nodes. "
            "This table feeds cohort retention dashboards in the serving layer."
        ),
        entity_impact=(
            "No graph entity mapping. Feeds cohort retention dashboards "
            "in the serving layer."
        ),
        decided_by=_DECIDED_BY,
        decided_at=_DECIDED_AT,
    ),

    "fct_team_daily_growth": InclusionDecision(
        source_name="fct_team_daily_growth",
        inclusion_mode="feature_source",
        decision_reason=(
            "Team daily growth metrics (new fans, fan churn, net growth rate) "
            "are time-series aggregates at the team level that feed team "
            "analytics model features. They do not introduce a new entity — "
            "the Team node already exists from dim_teams. Attaching daily "
            "growth snapshots as graph nodes would produce an impractically "
            "large temporal fan-out."
        ),
        entity_impact=(
            "No graph entity mapping. Feeds team analytics model feature "
            "computation."
        ),
        decided_by=_DECIDED_BY,
        decided_at=_DECIDED_AT,
    ),

    "dim_influencer_leagues": InclusionDecision(
        source_name="dim_influencer_leagues",
        inclusion_mode="graph_core",
        decision_reason=(
            "Influencer leagues are a distinct league type created by or for "
            "social media influencers, separate from standard private leagues. "
            "The InfluencerLeague node models this distinction and enables "
            "PROMOTES relationship analysis (InfluencerLeague → PrivateLeague)."
        ),
        entity_impact=(
            "Creates InfluencerLeague nodes. Feeds PROMOTES relationship "
            "(InfluencerLeague → PrivateLeague)."
        ),
        decided_by=_DECIDED_BY,
        decided_at=_DECIDED_AT,
    ),

    # Excluded
    

    "__drizzle_migrations": InclusionDecision(
        source_name="__drizzle_migrations",
        inclusion_mode="excluded",
        decision_reason=(
            "This is an internal Drizzle ORM migration tracking table created "
            "and managed automatically by the ORM framework. It contains no "
            "user data, business events, or analytical signals. Including it "
            "in any pipeline would be an error."
        ),
        entity_impact="No graph entity mapping. Excluded from all pipelines.",
        decided_by=_DECIDED_BY,
        decided_at=_DECIDED_AT,
    ),
}


# Lookup helper


def get_decision(source_name: str) -> InclusionDecision | None:
    """
    Return the inclusion decision for a source, or None if not recorded.

    Args:
        source_name: Canonical warehouse table name.

    Returns:
        InclusionDecision or None.
    """
    return INCLUSION_DECISIONS.get(source_name)


# Completeness validator


def assert_all_sources_have_decisions(registry_keys: set[str]) -> None:
    """
    Assert that every source in the registry has a documented decision.

    This should be called at startup or in the source inventory audit script
    to catch any table that was added to the registry without a corresponding
    decision entry.

    Args:
        registry_keys: Set of source names from the registry
            (typically get_all_source_names() from registry.py).

    Raises:
        SourceInventoryError: If any registry source has no decision entry,
            listing all missing sources.
    """
    decision_keys = set(INCLUSION_DECISIONS.keys())
    missing = sorted(registry_keys - decision_keys)
    undeclared = sorted(decision_keys - registry_keys)

    if missing:
        logger.error(
            "Source registry has entries without inclusion decisions",
            extra={"missing_decisions": missing, "count": len(missing)},
        )

    if undeclared:
        logger.warning(
            "Inclusion decisions exist for sources not in the registry",
            extra={"undeclared_sources": undeclared, "count": len(undeclared)},
        )

    if missing:
        raise SourceInventoryError(
            "All registry sources must have a documented inclusion decision",
            missing_decisions=missing,
            missing_count=len(missing),
        )