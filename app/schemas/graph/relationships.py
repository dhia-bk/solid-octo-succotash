"""
Graph relationship type contracts for Project Pulse Knowledge Graph.

This file defines every relationship type written to Neo4j as a typed Python
dataclass. It is the canonical contract between the transformer layer and
the loader/merge-query layer.

Design rules:
- One dataclass per relationship type in constants.GRAPH_RELATIONSHIP_TYPES.
- Every dataclass has start_node_id, end_node_id, and rel_type fields.
- rel_type defaults to the constant value — transformers must not override it.
- Relationship properties follow the same rules as node properties:
    - Timestamps: str | None (ISO strings written directly to Neo4j)
    - Booleans: bool | None (not int)
    - No warehouse-layer types
- Relationships with no properties beyond the three required fields use
  dataclass(frozen=True) with field defaults for rel_type only.
- The RELATIONSHIP_CLASS_REGISTRY at the bottom maps every type constant
  to its class for use by loaders and validators.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.core.constants import (
    ABOUT,
    ACHIEVED,
    AWAY_TEAM,
    AWARDED,
    CHALLENGED,
    COMMENTED,
    CURRENT_STATE,
    DIRECT_MESSAGE,
    DISCUSSED,
    EQUIPPED,
    EXHIBITS,
    EXPRESSED,
    FAVORS,
    GENERATED_FOR,
    LIKED,
    ANSWERED,
    FRIENDED,
    HAS_AFFINITY,
    HAS_FIXTURE,
    HAS_MESSAGE,
    HAS_RATING,
    HAS_STATE,
    HAS_TAG,
    HAS_THEME,
    HOME_TEAM,
    IN_LEAGUE,
    JOINED_DISCUSSION,
    MEMBER_OF,
    MODERATED,
    PARTICIPATED_IN,
    PLAYED_IN,
    PLAYS_IN,
    POSTED,
    PREDICTED,
    PREVIOUS_STATE,
    PROMOTES,
    PURCHASED,
    RECEIVED_NOTIFICATION,
    REDEEMED,
    REPLIES_TO,
    SPENT,
    SUBSCRIBED_TO,
    TALKED_TO,
    USED_TOOL,
)

# ============================================================================
# Identity
# ============================================================================


@dataclass(frozen=True)
class EquippedRel:
    """User → Avatar"""
    start_node_id: str
    end_node_id: str
    rel_type: str = field(default=EQUIPPED, init=False)


@dataclass(frozen=True)
class AwardedRel:
    """User → Badge"""
    start_node_id: str
    end_node_id: str
    rel_type: str = field(default=AWARDED, init=False)


@dataclass(frozen=True)
class FavorsRel:
    """User → Team (favorite team relationship)"""
    start_node_id: str
    end_node_id: str
    rel_type: str = field(default=FAVORS, init=False)


# ============================================================================
# Sports core
# ============================================================================


@dataclass(frozen=True)
class PlaysInRel:
    """Team → League"""
    start_node_id: str
    end_node_id: str
    rel_type: str = field(default=PLAYS_IN, init=False)


@dataclass(frozen=True)
class HomeTeamRel:
    """Match → Team (home side)"""
    start_node_id: str
    end_node_id: str
    rel_type: str = field(default=HOME_TEAM, init=False)


@dataclass(frozen=True)
class AwayTeamRel:
    """Match → Team (away side)"""
    start_node_id: str
    end_node_id: str
    rel_type: str = field(default=AWAY_TEAM, init=False)


@dataclass(frozen=True)
class InLeagueRel:
    """Match → League"""
    start_node_id: str
    end_node_id: str
    rel_type: str = field(default=IN_LEAGUE, init=False)


# ============================================================================
# Social
# ============================================================================


@dataclass(frozen=True)
class MemberOfRel:
    """
    User → PrivateLeague

    Carries membership metadata as edge properties so that role, join date,
    and activity status are queryable without hitting the membership fact table.
    """
    start_node_id: str
    end_node_id: str
    role: str | None
    joined_at: str | None
    is_active: bool | None
    rel_type: str = field(default=MEMBER_OF, init=False)


@dataclass(frozen=True)
class HasThemeRel:
    """PrivateLeague → LeagueTheme"""
    start_node_id: str
    end_node_id: str
    rel_type: str = field(default=HAS_THEME, init=False)


@dataclass(frozen=True)
class PromotesRel:
    """InfluencerLeague → PrivateLeague"""
    start_node_id: str
    end_node_id: str
    rel_type: str = field(default=PROMOTES, init=False)


@dataclass(frozen=True)
class PostedRel:
    """User → Post"""
    start_node_id: str
    end_node_id: str
    published_at: str | None
    rel_type: str = field(default=POSTED, init=False)


@dataclass(frozen=True)
class CommentedRel:
    """User → Comment"""
    start_node_id: str
    end_node_id: str
    created_at: str | None
    rel_type: str = field(default=COMMENTED, init=False)


@dataclass(frozen=True)
class RepliesToRel:
    """
    Comment → Comment

    start_node_id = child comment_id
    end_node_id   = parent comment_id
    """
    start_node_id: str
    end_node_id: str
    rel_type: str = field(default=REPLIES_TO, init=False)


@dataclass(frozen=True)
class JoinedDiscussionRel:
    """User → Discussion"""
    start_node_id: str
    end_node_id: str
    event_type: str | None
    event_at: str | None
    rel_type: str = field(default=JOINED_DISCUSSION, init=False)


@dataclass(frozen=True)
class DirectMessageRel:
    """User → DirectPair"""
    start_node_id: str
    end_node_id: str
    rel_type: str = field(default=DIRECT_MESSAGE, init=False)


# ============================================================================
# Competition
# ============================================================================


@dataclass(frozen=True)
class PredictedRel:
    """
    User → Match

    Carries prediction outcome metadata as edge properties. This is the
    primary signal for tribe detection and persona modeling.
    """
    start_node_id: str
    end_node_id: str
    prediction_id: str | None
    predicted_at: str | None
    predicted_outcome: str | None
    points_awarded: int | None
    is_correct_result: bool | None
    prediction_era: str | None
    rel_type: str = field(default=PREDICTED, init=False)


@dataclass(frozen=True)
class ChallengedRel:
    """
    User → Duel

    start_node_id = sender_user_id
    """
    start_node_id: str
    end_node_id: str
    entry_fee: int | None
    rel_type: str = field(default=CHALLENGED, init=False)


@dataclass(frozen=True)
class ParticipatedInRel:
    """
    User → Super6Round or LMSCompetition

    Used for both Super6 and LMS competition participation. The target node
    type is determined by end_node_id's node label in the graph.
    """
    start_node_id: str
    end_node_id: str
    joined_at: str | None
    total_points: int | None
    is_winner: bool | None
    rel_type: str = field(default=PARTICIPATED_IN, init=False)


@dataclass(frozen=True)
class HasFixtureRel:
    """Super6Round → Match"""
    start_node_id: str
    end_node_id: str
    rel_type: str = field(default=HAS_FIXTURE, init=False)


@dataclass(frozen=True)
class AboutRel:
    """PredictionDiscussion → Match"""
    start_node_id: str
    end_node_id: str
    rel_type: str = field(default=ABOUT, init=False)


# ============================================================================
# Intelligence / persona
# ============================================================================


@dataclass(frozen=True)
class ExhibitsRel:
    """User → PersonaState (historical state chain)"""
    start_node_id: str
    end_node_id: str
    rel_type: str = field(default=EXHIBITS, init=False)


@dataclass(frozen=True)
class CurrentStateRel:
    """User → PersonaState (the most recent state)"""
    start_node_id: str
    end_node_id: str
    rel_type: str = field(default=CURRENT_STATE, init=False)


@dataclass(frozen=True)
class PreviousStateRel:
    """
    PersonaState → PersonaState

    Links a state to the one that preceded it in the temporal chain.
    start_node_id = current state
    end_node_id   = previous state
    """
    start_node_id: str
    end_node_id: str
    rel_type: str = field(default=PREVIOUS_STATE, init=False)


@dataclass(frozen=True)
class HasStateRel:
    """User → PersonaState (all historical states, not just current)"""
    start_node_id: str
    end_node_id: str
    calculated_at: str | None
    rel_type: str = field(default=HAS_STATE, init=False)


@dataclass(frozen=True)
class DiscussedRel:
    """User → Topic"""
    start_node_id: str
    end_node_id: str
    rel_type: str = field(default=DISCUSSED, init=False)


@dataclass(frozen=True)
class ExpressedRel:
    """User → Sentiment"""
    start_node_id: str
    end_node_id: str
    rel_type: str = field(default=EXPRESSED, init=False)


@dataclass(frozen=True)
class HasAffinityRel:
    """
    User → Team

    Carries computed affinity signals as edge properties. These are the
    primary signals for fan behaviour analysis and content targeting.
    """
    start_node_id: str
    end_node_id: str
    affinity_type: str | None
    total_predictions: int | None
    prediction_accuracy_rate: float | None
    is_favorite_team: bool | None
    is_active_fan: bool | None
    calculated_at: str | None
    rel_type: str = field(default=HAS_AFFINITY, init=False)


@dataclass(frozen=True)
class HasRatingRel:
    """User → RatingSnapshot"""
    start_node_id: str
    end_node_id: str
    rel_type: str = field(default=HAS_RATING, init=False)


# ============================================================================
# AI / communication
# ============================================================================


@dataclass(frozen=True)
class TalkedToRel:
    """User → ChatbotConversation"""
    start_node_id: str
    end_node_id: str
    conversation_start: str | None
    rel_type: str = field(default=TALKED_TO, init=False)


@dataclass(frozen=True)
class HasMessageRel:
    """ChatbotConversation → ChatbotMessage"""
    start_node_id: str
    end_node_id: str
    message_order: int | None
    rel_type: str = field(default=HAS_MESSAGE, init=False)


@dataclass(frozen=True)
class UsedToolRel:
    """ChatbotMessage → ToolCall"""
    start_node_id: str
    end_node_id: str
    tool_name: str | None
    rel_type: str = field(default=USED_TOOL, init=False)


# ============================================================================
# Economy
# ============================================================================


@dataclass(frozen=True)
class SpentRel:
    """User → CoinTransaction"""
    start_node_id: str
    end_node_id: str
    coin_amount: int | None
    event_at: str | None
    rel_type: str = field(default=SPENT, init=False)


@dataclass(frozen=True)
class PurchasedRel:
    """User → Voucher"""
    start_node_id: str
    end_node_id: str
    purchase_id: str | None
    coin_cost: int | None
    purchase_date: str | None
    rel_type: str = field(default=PURCHASED, init=False)


@dataclass(frozen=True)
class RedeemedRel:
    """User → PartnerReward"""
    start_node_id: str
    end_node_id: str
    redemption_id: str | None
    redeemed_at: str | None
    quantity: int | None
    rel_type: str = field(default=REDEEMED, init=False)


@dataclass(frozen=True)
class SubscribedToRel:
    """User → SubscriptionProduct"""
    start_node_id: str
    end_node_id: str
    event_type: str | None
    event_timestamp: str | None
    amount_paid_usd: float | None
    is_active: bool | None
    rel_type: str = field(default=SUBSCRIBED_TO, init=False)


@dataclass(frozen=True)
class AchievedRel:
    """User → Achievement"""
    start_node_id: str
    end_node_id: str
    earned_at: str | None
    rel_type: str = field(default=ACHIEVED, init=False)


# ============================================================================
# Engagement / content
# ============================================================================


@dataclass(frozen=True)
class HasTagRel:
    """
    Post → Tag, News → Tag, or AIArticle → Tag

    owner_type identifies which node type the tag is attached to.
    This allows a single relationship type to serve all three content
    entity types without ambiguity.
    """
    start_node_id: str
    end_node_id: str
    owner_type: str | None
    rel_type: str = field(default=HAS_TAG, init=False)


@dataclass(frozen=True)
class ReceivedNotificationRel:
    """User → NotificationContent"""
    start_node_id: str
    end_node_id: str
    notification_id: str | None
    sent_at: str | None
    is_read: bool | None
    read_at: str | None
    rel_type: str = field(default=RECEIVED_NOTIFICATION, init=False)


# ============================================================================
# Moderation / content
# ============================================================================


@dataclass(frozen=True)
class ModeratedRel:
    """
    User → ModerationEvent

    start_node_id = moderator_user_id
    end_node_id   = moderation_event_id
    """
    start_node_id: str
    end_node_id: str
    rel_type: str = field(default=MODERATED, init=False)


@dataclass(frozen=True)
class GeneratedForRel:
    """
    AIArticle → Match or AIArticle → News

    The target node type is resolved by the transformer from the
    published_news_id and match_id fields on the AIArticle source row.
    """
    start_node_id: str
    end_node_id: str
    rel_type: str = field(default=GENERATED_FOR, init=False)


@dataclass(frozen=True)
class PlayedInRel:
    """
    User → Match

    Used in contexts where a user participated in match-related events
    (discussions, duels) beyond direct prediction, where PREDICTED does
    not apply.
    """
    start_node_id: str
    end_node_id: str
    rel_type: str = field(default=PLAYED_IN, init=False)

# ============================================================================
# Activity engagement
# ============================================================================


@dataclass(frozen=True)
class LikedRel:
    """User → Post or User → Comment"""
    start_node_id: str
    end_node_id: str
    target_type: str | None
    activity_at: str | None
    rel_type: str = field(default=LIKED, init=False)


@dataclass(frozen=True)
class AnsweredRel:
    """User → Poll"""
    start_node_id: str
    end_node_id: str
    activity_at: str | None
    rel_type: str = field(default=ANSWERED, init=False)


@dataclass(frozen=True)
class FriendedRel:
    """User → User"""
    start_node_id: str
    end_node_id: str
    activity_at: str | None
    rel_type: str = field(default=FRIENDED, init=False)

# ============================================================================
# Relationship class registry
# Maps every relationship type constant to its dataclass for use by
# loaders and validators.
# ============================================================================

RELATIONSHIP_CLASS_REGISTRY: dict[str, type] = {
    EQUIPPED: EquippedRel,
    AWARDED: AwardedRel,
    FAVORS: FavorsRel,
    PLAYS_IN: PlaysInRel,
    HOME_TEAM: HomeTeamRel,
    AWAY_TEAM: AwayTeamRel,
    IN_LEAGUE: InLeagueRel,
    MEMBER_OF: MemberOfRel,
    HAS_THEME: HasThemeRel,
    PROMOTES: PromotesRel,
    POSTED: PostedRel,
    COMMENTED: CommentedRel,
    REPLIES_TO: RepliesToRel,
    JOINED_DISCUSSION: JoinedDiscussionRel,
    DIRECT_MESSAGE: DirectMessageRel,
    PREDICTED: PredictedRel,
    CHALLENGED: ChallengedRel,
    PARTICIPATED_IN: ParticipatedInRel,
    HAS_FIXTURE: HasFixtureRel,
    ABOUT: AboutRel,
    EXHIBITS: ExhibitsRel,
    CURRENT_STATE: CurrentStateRel,
    PREVIOUS_STATE: PreviousStateRel,
    HAS_STATE: HasStateRel,
    DISCUSSED: DiscussedRel,
    EXPRESSED: ExpressedRel,
    HAS_AFFINITY: HasAffinityRel,
    HAS_RATING: HasRatingRel,
    TALKED_TO: TalkedToRel,
    HAS_MESSAGE: HasMessageRel,
    USED_TOOL: UsedToolRel,
    SPENT: SpentRel,
    PURCHASED: PurchasedRel,
    REDEEMED: RedeemedRel,
    SUBSCRIBED_TO: SubscribedToRel,
    ACHIEVED: AchievedRel,
    HAS_TAG: HasTagRel,
    RECEIVED_NOTIFICATION: ReceivedNotificationRel,
    MODERATED: ModeratedRel,
    GENERATED_FOR: GeneratedForRel,
    PLAYED_IN: PlayedInRel,
    LIKED: LikedRel,
    ANSWERED: AnsweredRel,
    FRIENDED: FriendedRel,
}