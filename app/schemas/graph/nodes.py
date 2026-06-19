"""
Graph node type contracts for Project Pulse Knowledge Graph.

This file defines every node type written to Neo4j as a typed Python
dataclass. It is the canonical contract between the transformer layer
and the loader/merge-query layer.

Design rules:
- One dataclass per node label in constants.GRAPH_NODE_LABELS.
- id is always str — the stable node identifier used in MERGE queries.
- Timestamps are str | None (ISO 8601 strings written directly to Neo4j).
- Boolean flags are bool | None (not int — graph properties use native bool).
- No warehouse-layer types appear here (no TINYINT, no DECIMAL).
- The NODE_CLASS_REGISTRY at the bottom maps every label constant to its class.

The id field comment on each class documents which id helper from
app.core.ids should be used by the transformer to generate it.
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

# ============================================================================
# Identity
# ============================================================================


@dataclass(frozen=True)
class UserNode:
    """
    Graph node: User

    id: build_user_id(user_id)
    """

    id: str
    user_name: str | None
    full_name: str | None
    country: str | None
    gender: str | None
    age: int | None
    birthdate: str | None
    user_created_at: str | None
    last_activity_at: str | None
    favorite_team_id: str | None
    current_subscription_name: str | None
    is_suspended: bool | None
    duel_rating: float | None
    avatar_id: str | None
    auth_provider: str | None
    ai_remaining_credits: int | None


@dataclass(frozen=True)
class AvatarNode:
    """
    Graph node: Avatar

    id: build_avatar_id(avatar_id)
    """

    id: str
    avatar_name: str | None
    avatar_image: str | None
    avatar_description: str | None
    users_unlocked: int | None
    adoption_rate: float | None


@dataclass(frozen=True)
class BadgeNode:
    """
    Graph node: Badge

    id: build_badge_id(badge_id)
    """

    id: str
    badge_name: str | None
    badge_image: str | None
    badge_description: str | None
    users_awarded: int | None
    adoption_rate: float | None


# ============================================================================
# Sports core
# ============================================================================


@dataclass(frozen=True)
class TeamNode:
    """
    Graph node: Team

    id: build_team_id(team_id)
    """

    id: str
    team_name: str | None
    team_code: str | None
    country: str | None
    venue_name: str | None
    team_logo: str | None
    total_fans: int | None
    fan_rank: int | None
    fan_engagement_score: float | None
    fan_growth_rate: float | None


@dataclass(frozen=True)
class LeagueNode:
    """
    Graph node: League

    id: build_league_id(league_id)
    """

    id: str
    league_name: str | None
    country: str | None
    season: str | None
    league_logo: str | None
    is_active: bool | None


@dataclass(frozen=True)
class MatchNode:
    """
    Graph node: Match

    id: build_fixture_id(fixture_id)
    """

    id: str
    home_team_id: str | None
    away_team_id: str | None
    league_id: str | None
    kickoff_at: str | None
    status: str | None
    final_game_score: str | None
    result_known: bool | None
    fixture_era: str | None


# ============================================================================
# Social
# ============================================================================


@dataclass(frozen=True)
class PrivateLeagueNode:
    """
    Graph node: PrivateLeague

    id: build_private_league_id(private_league_id)
    """

    id: str
    league_name: str | None
    owner_user_id: str | None
    member_count: int | None
    is_generic: bool | None


@dataclass(frozen=True)
class LeagueThemeNode:
    """
    Graph node: LeagueTheme

    id: slugify(str(theme_id) + "_theme") or
        slugify(str(private_league_id) + "_theme") if theme_id is null
    """

    id: str
    private_league_id: str | None
    background_color: str | None
    accent_color: str | None
    banner_url: str | None


@dataclass(frozen=True)
class InfluencerLeagueNode:
    """
    Graph node: InfluencerLeague

    id: normalize_string_id(influencer_league_id)
    """

    id: str
    name: str | None
    description: str | None
    created_at: str | None


@dataclass(frozen=True)
class PostNode:
    """
    Graph node: Post

    id: build_post_id(post_id)
    """

    id: str
    author_user_id: str | None
    title: str | None
    published_at: str | None
    like_count: int | None
    view_count: int | None
    is_active: bool | None


@dataclass(frozen=True)
class CommentNode:
    """
    Graph node: Comment

    id: build_comment_id(comment_id)
    """

    id: str
    user_id: str | None
    post_id: str | None
    parent_comment_id: str | None
    created_at: str | None
    like_count: int | None


@dataclass(frozen=True)
class DiscussionNode:
    """
    Graph node: Discussion

    id: build_discussion_id(discussion_id)
    """

    id: str
    fixture_id: str | None
    created_at: str | None
    is_closed: bool | None


@dataclass(frozen=True)
class PredictionDiscussionNode:
    """
    Graph node: PredictionDiscussion

    id: normalize_string_id(prediction_discussion_id)
    """

    id: str
    prediction_id: str | None
    discussion_type: str | None
    created_at: str | None


@dataclass(frozen=True)
class ConversationNode:
    """
    Graph node: Conversation

    id: normalize_string_id(conversation_id)
    """

    id: str
    conversation_type: str | None
    private_league_id: str | None
    created_by_user_id: str | None
    is_active: bool | None
    total_messages: int | None
    participant_count: int | None


@dataclass(frozen=True)
class DirectPairNode:
    """
    Graph node: DirectPair

    id: normalize_string_id(direct_pair_key)
    The direct_pair_key is already order-normalized in the DWH.
    """

    id: str
    user_a_id: str | None
    user_b_id: str | None
    total_messages: int | None
    first_message_at: str | None
    last_message_at: str | None


# ============================================================================
# Intelligence
# ============================================================================


@dataclass(frozen=True)
class PersonaStateNode:
    """
    Graph node: PersonaState

    id: build_persona_state_snapshot_key(user_id, pcm_stage, calculated_at)
    """

    id: str
    user_id: str | None
    pcm_stage: str | None
    behaviour_label: str | None
    birfing_coefficient: float | None
    frustration_bias: float | None
    calculated_at: str | None


@dataclass(frozen=True)
class TopicNode:
    """
    Graph node: Topic

    id: build_topic_id(id)
    """

    id: str
    topic_label: str | None
    source_type: str | None
    item_id: str | None
    user_id: str | None
    processed_at: str | None
    model_version: str | None


@dataclass(frozen=True)
class SentimentNode:
    """
    Graph node: Sentiment

    id: stable_hash_key(source_type, item_id, user_id)
    """

    id: str
    source_type: str | None
    item_id: str | None
    user_id: str | None
    sentiment_label: str | None
    score_positive: float | None
    score_negative: float | None
    score_neutral: float | None
    language_code: str | None
    processed_at: str | None


@dataclass(frozen=True)
class RatingSnapshotNode:
    """
    Graph node: RatingSnapshot

    id: normalize_string_id(rating_event_id)
    """

    id: str
    user_id: str | None
    duel_id: str | None
    previous_rating: float | None
    new_rating: float | None
    change_amount: float | None
    reason: str | None
    created_at: str | None


# ============================================================================
# AI / communication
# ============================================================================


@dataclass(frozen=True)
class ChatbotConversationNode:
    """
    Graph node: ChatbotConversation

    id: build_chatbot_conversation_id(conversation_id)
    """

    id: str
    user_id: str | None
    source: str | None
    conversation_start: str | None
    duration_seconds: int | None
    total_messages: int | None
    total_tool_calls: int | None
    model_family: str | None


@dataclass(frozen=True)
class ChatbotMessageNode:
    """
    Graph node: ChatbotMessage

    id: build_chatbot_message_id(message_id)
    """

    id: str
    conversation_id: str | None
    user_id: str | None
    message_at: str | None
    message_type: str | None
    agent_name: str | None
    model_name: str | None
    total_tokens: int | None


@dataclass(frozen=True)
class ToolCallNode:
    """
    Graph node: ToolCall

    id: build_tool_call_id(tool_call_id)
    """

    id: str
    message_id: str | None
    tool_name: str | None
    tool_call_at: str | None


@dataclass(frozen=True)
class ToolNode:
    """
    Graph node: Tool

    id: slugify(tool_name)
    Represents the canonical tool entity (deduplicated across all invocations).
    """

    id: str
    tool_name: str


# ============================================================================
# Economy
# ============================================================================


@dataclass(frozen=True)
class CoinTransactionNode:
    """
    Graph node: CoinTransaction

    id: normalize_string_id(event_id)

    Note: coin_amount and coin_balance_after are stored as int in the graph
    (truncated from DECIMAL at the transformer layer). If sub-unit precision
    is required, revisit before going to production.
    """

    id: str
    user_id: str | None
    transaction_type: str | None
    event_type: str | None
    coin_amount: int | None
    coin_balance_after: int | None
    event_at: str | None


@dataclass(frozen=True)
class VoucherNode:
    """
    Graph node: Voucher

    id: build_voucher_id(voucher_key)
    """

    id: str
    voucher_title: str | None
    advertiser_name: str | None
    acquisition_type: str | None
    coin_cost: int | None
    is_active: bool | None
    expiry_date: str | None


@dataclass(frozen=True)
class PartnerRewardNode:
    """
    Graph node: PartnerReward

    id: build_reward_id(reward_key)
    """

    id: str
    partner_name: str | None
    reward_title: str | None
    reward_type: str | None
    coin_cost: int | None
    is_active: bool | None
    stock_remaining: int | None


@dataclass(frozen=True)
class SubscriptionProductNode:
    """
    Graph node: SubscriptionProduct

    id: normalize_string_id(subscription_type_id)
    """

    id: str
    subscription_name: str | None
    subscription_price: float | None
    duration_in_days: int | None


@dataclass(frozen=True)
class AchievementNode:
    """
    Graph node: Achievement

    id: build_achievement_id(award_id)

    Note: reward_amount is stored as int in the graph (coin amounts are
    whole numbers in the platform economy).
    """

    id: str
    achievement_type: str | None
    badge_name: str | None
    trophy_name: str | None
    reward_amount: int | None
    earned_at: str | None


@dataclass(frozen=True)
class FinancialEventNode:
    """
    Graph node: FinancialEvent

    id: normalize_string_id(event_id)
    """

    id: str
    user_id: str | None
    event_type: str | None
    amount: float | None
    currency: str | None
    payment_status: str | None
    event_at: str | None


# ============================================================================
# Competition
# ============================================================================


@dataclass(frozen=True)
class DuelNode:
    """
    Graph node: Duel

    id: build_duel_id(duel_id)
    """

    id: str
    fixture_id: str | None
    sender_user_id: str | None
    receiver_user_id: str | None
    entry_fee: int | None
    status: str | None
    winner_user_id: str | None
    created_at: str | None


@dataclass(frozen=True)
class Super6RoundNode:
    """
    Graph node: Super6Round

    id: build_super6_round_id(super6_round_id)
    """

    id: str
    round_number: int | None
    start_date: str | None
    end_date: str | None
    is_active: bool | None


@dataclass(frozen=True)
class LMSCompetitionNode:
    """
    Graph node: LMSCompetition

    id: build_lms_competition_id(lms_competition_id)
    """

    id: str
    competition_name: str | None
    private_league_id: str | None
    status: str | None
    entry_fee_coins: int | None
    prize_pool_coins: int | None


# ============================================================================
# Engagement / gamification
# ============================================================================


@dataclass(frozen=True)
class PollNode:
    """
    Graph node: Poll

    id: build_poll_id(fixture_poll_id)
    """

    id: str
    fixture_id: str | None
    creator_user_id: str | None
    question_text: str | None
    total_responses: int | None
    is_active: bool | None


@dataclass(frozen=True)
class QuestionNode:
    """
    Graph node: Question

    id: build_question_id(question_id)
    """

    id: str
    question_text: str | None
    created_at: str | None
    is_active: bool | None
    total_responses: int | None


@dataclass(frozen=True)
class QuizNode:
    """
    Graph node: Quiz

    id: build_quiz_id(quiz_id)
    """

    id: str
    quiz_name: str | None
    creator_user_id: str | None
    created_at: str | None
    total_questions: int | None
    is_active: bool | None


@dataclass(frozen=True)
class QuizQuestionNode:
    """
    Graph node: QuizQuestion

    id: build_quiz_question_id(quiz_question_id)
    """

    id: str
    question_text: str | None
    difficulty_level: str | None
    total_attempts: int | None
    accuracy_rate: float | None
    is_active: bool | None


@dataclass(frozen=True)
class TagNode:
    """
    Graph node: Tag

    id: build_tag_id(tag_id)
    """

    id: str
    tag_name: str | None
    tag_url: str | None
    is_trending: bool | None
    trending_score: float | None
    team_id: str | None
    league_id: str | None


# ============================================================================
# Notifications / moderation / content
# ============================================================================


@dataclass(frozen=True)
class NotificationContentNode:
    """
    Graph node: NotificationContent

    id: build_notification_content_id(content_id)
    """

    id: str
    sender_user_id: str | None
    normalized_message_text: str | None
    first_seen_at: str | None
    last_seen_at: str | None


@dataclass(frozen=True)
class ModerationEventNode:
    """
    Graph node: ModerationEvent

    id: build_moderation_event_id(event_id)
    """

    id: str
    moderator_user_id: str | None
    target_user_id: str | None
    moderation_type: str | None
    status: str | None
    event_at: str | None
    automated_flag: bool | None
    decision_confidence_score: float | None


@dataclass(frozen=True)
class AIArticleNode:
    """
    Graph node: AIArticle

    id: build_ai_article_id(article_id)
    """

    id: str
    article_type: str | None
    content_category: str | None
    match_id: str | None
    status: str | None
    published_at: str | None
    view_count: int | None
    like_count: int | None


@dataclass(frozen=True)
class NewsNode:
    """
    Graph node: News

    id: build_news_id(news_id)
    """

    id: str
    title: str | None
    author: str | None
    published_at: str | None
    url: str | None
    is_active: bool | None


# ============================================================================
# Node class registry
# Maps every label constant to its dataclass for use by loaders and validators.
# ============================================================================

NODE_CLASS_REGISTRY: dict[str, type] = {
    USER: UserNode,
    AVATAR: AvatarNode,
    BADGE: BadgeNode,
    TEAM: TeamNode,
    LEAGUE: LeagueNode,
    MATCH: MatchNode,
    PRIVATE_LEAGUE: PrivateLeagueNode,
    LEAGUE_THEME: LeagueThemeNode,
    INFLUENCER_LEAGUE: InfluencerLeagueNode,
    POST: PostNode,
    COMMENT: CommentNode,
    DISCUSSION: DiscussionNode,
    PREDICTION_DISCUSSION: PredictionDiscussionNode,
    CONVERSATION: ConversationNode,
    DIRECT_PAIR: DirectPairNode,
    PERSONA_STATE: PersonaStateNode,
    TOPIC: TopicNode,
    SENTIMENT: SentimentNode,
    RATING_SNAPSHOT: RatingSnapshotNode,
    CHATBOT_CONVERSATION: ChatbotConversationNode,
    CHATBOT_MESSAGE: ChatbotMessageNode,
    TOOL_CALL: ToolCallNode,
    TOOL: ToolNode,
    COIN_TRANSACTION: CoinTransactionNode,
    VOUCHER: VoucherNode,
    PARTNER_REWARD: PartnerRewardNode,
    SUBSCRIPTION_PRODUCT: SubscriptionProductNode,
    ACHIEVEMENT: AchievementNode,
    FINANCIAL_EVENT: FinancialEventNode,
    DUEL: DuelNode,
    SUPER6_ROUND: Super6RoundNode,
    LMS_COMPETITION: LMSCompetitionNode,
    POLL: PollNode,
    QUESTION: QuestionNode,
    QUIZ: QuizNode,
    QUIZ_QUESTION: QuizQuestionNode,
    TAG: TagNode,
    NOTIFICATION_CONTENT: NotificationContentNode,
    MODERATION_EVENT: ModerationEventNode,
    AI_ARTICLE: AIArticleNode,
    NEWS: NewsNode,
}