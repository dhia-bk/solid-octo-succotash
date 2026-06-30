"""
Node loader — loads NodeRecord instances from a GraphWriteBatch into Neo4j.

Flow per batch:
1. validate_graph_write_batch(batch) — pre-load validation
2. Group NodeRecords by (label, source_name)
3. For each group, look up merge query from MergeQueryRegistry
4. Delegate to BatchWriter.write_nodes()
5. Return LoadResult
"""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Callable
from time import perf_counter
from typing import Any

from app.contracts.graph_records import GraphWriteBatch, NodeRecord
from app.core.constants import DEFAULT_BATCH_SIZE
from app.core.exceptions import LoaderError
from app.core.logging import get_logger, log_event, log_load_finished, log_load_started
from app.db.neo4j_client import Neo4jClient
from app.loaders.base import BaseLoader, LoadResult
from app.loaders.batch_writer import BatchWriter
from app.validation.transform_checks import validate_graph_write_batch


class MergeQueryRegistry:
    """
    Registry mapping (label, source_name) → node merge query string
    and (rel_type, source_name[, end_label]) → relationship merge query string.

    Built by build_merge_query_registry() from merge_queries/ modules.
    """

    def __init__(self) -> None:
        self._node_queries: dict[tuple[str, str], str] = {}
        self._rel_queries: dict[tuple[str, str, str | None], str] = {}

    def register_node_query(
        self,
        label: str,
        source_name: str,
        query: str,
    ) -> None:
        """Register a merge query for a (label, source_name) pair."""
        key = (label, source_name)
        if key in self._node_queries:
            raise LoaderError(
                "Duplicate node merge query registration",
                label=label,
                source_name=source_name,
            )
        self._node_queries[key] = query

    def register_rel_query(
        self,
        rel_type: str,
        source_name: str,
        query: str,
        end_label: str | None = None,
    ) -> None:
        """Register a merge query for a (rel_type, source_name[, end_label]) triple."""
        key = (rel_type, source_name, end_label)
        if key in self._rel_queries:
            raise LoaderError(
                "Duplicate relationship merge query registration",
                rel_type=rel_type,
                source_name=source_name,
                end_label=end_label,
            )
        self._rel_queries[key] = query

    def get_node_query(self, label: str, source_name: str) -> str | None:
        """Return the merge query for a (label, source_name) pair, or None."""
        return self._node_queries.get((label, source_name))

    def get_rel_query(
        self,
        rel_type: str,
        source_name: str,
        end_label: str | None = None,
    ) -> str | None:
        """
        Return the merge query for a (rel_type, source_name[, end_label]) triple.

        Tries end_label-specific key first, then falls back to (rel_type, source_name, None).
        """
        if end_label is not None:
            query = self._rel_queries.get((rel_type, source_name, end_label))
            if query is not None:
                return query
        return self._rel_queries.get((rel_type, source_name, None))

    def has_node_query(self, label: str, source_name: str) -> bool:
        """Return True if a node query is registered for the pair."""
        return (label, source_name) in self._node_queries

    def has_rel_query(
        self,
        rel_type: str,
        source_name: str,
        end_label: str | None = None,
    ) -> bool:
        """Return True if a rel query is registered for the triple."""
        return self.get_rel_query(rel_type, source_name, end_label) is not None


def build_merge_query_registry() -> MergeQueryRegistry:
    """
    Build and return a populated MergeQueryRegistry.

    Imports all merge_queries/ domain modules and registers their queries.
    Called once at pipeline startup.
    """
    registry = MergeQueryRegistry()
    _register_node_queries(registry)
    _register_rel_queries(registry)
    return registry


def _register_node_queries(registry: MergeQueryRegistry) -> None:
    """Register all node merge queries from domain modules."""
    from app.loaders.merge_queries import achievements as ach
    from app.loaders.merge_queries import ai_articles as ai_art
    from app.loaders.merge_queries import app_identity as app_id
    from app.loaders.merge_queries import avatars
    from app.loaders.merge_queries import badges
    from app.loaders.merge_queries import chatbot
    from app.loaders.merge_queries import chat_social
    from app.loaders.merge_queries import comments
    from app.loaders.merge_queries import competitions
    from app.loaders.merge_queries import discussions
    from app.loaders.merge_queries import duels
    from app.loaders.merge_queries import economy
    from app.loaders.merge_queries import fixtures
    from app.loaders.merge_queries import gamification
    from app.loaders.merge_queries import influencer_leagues
    from app.loaders.merge_queries import leagues
    from app.loaders.merge_queries import moderation
    from app.loaders.merge_queries import news
    from app.loaders.merge_queries import notifications
    from app.loaders.merge_queries import partner_rewards
    from app.loaders.merge_queries import personas
    from app.loaders.merge_queries import posts
    from app.loaders.merge_queries import private_leagues
    from app.loaders.merge_queries import rating_history
    from app.loaders.merge_queries import sentiment
    from app.loaders.merge_queries import subscriptions
    from app.loaders.merge_queries import tags
    from app.loaders.merge_queries import teams
    from app.loaders.merge_queries import themes
    from app.loaders.merge_queries import topics
    from app.loaders.merge_queries import users
    from app.loaders.merge_queries import vouchers

    for label, source_name, query_fn in [
        # Identity
        ("User",                "dim_users",                          users.get_user_merge_query),
        ("User",                "dim_notification_preferences",       users.get_user_enrichment_merge_query),
        ("Avatar",              "dim_avatars",                        avatars.get_avatar_merge_query),
        ("Badge",               "dim_badges",                         badges.get_badge_merge_query),
        # Sports
        ("Team",                "dim_teams",                          teams.get_team_merge_query),
        ("Team",                "dim_teams_enhanced",                 teams.get_team_enrichment_merge_query),
        ("League",              "dim_leagues",                        leagues.get_league_merge_query),
        ("Match",               "dim_fixtures",                       fixtures.get_match_merge_query),
        ("InfluencerLeague",    "dim_influencer_leagues",             influencer_leagues.get_influencer_league_merge_query),
        # Private leagues
        ("PrivateLeague",       "dim_private_leagues",                private_leagues.get_private_league_merge_query),
        ("LeagueTheme",         "dim_private_league_themes",          themes.get_league_theme_merge_query),
        # Social / content
        ("Post",                "dim_posts",                          posts.get_post_merge_query),
        ("Comment",             "dim_comments",                       comments.get_comment_merge_query),
        ("Discussion",          "dim_discussions",                    discussions.get_discussion_merge_query),
        ("PredictionDiscussion","dim_prediction_discussions",         discussions.get_prediction_discussion_merge_query),
        ("Conversation",        "dim_chat_conversations_mysql",       chat_social.get_conversation_merge_query),
        ("DirectPair",          "dim_chat_direct_pairs",              chat_social.get_direct_pair_merge_query),
        # Intelligence / behavior
        ("PersonaState",        "fct_user_behavior",                  personas.get_persona_state_merge_query),
        ("Topic",               "fct_topics",                         topics.get_topic_merge_query),
        ("Sentiment",           "fct_sentiment",                      sentiment.get_sentiment_merge_query),
        ("RatingSnapshot",      "fct_user_rating_history",            rating_history.get_rating_snapshot_merge_query),
        # Chatbot / AI
        ("ChatbotConversation", "dim_chatbot_conversations",          chatbot.get_chatbot_conversation_merge_query),
        ("ChatbotMessage",      "fct_chatbot_messages",               chatbot.get_chatbot_message_merge_query),
        ("ToolCall",            "fct_chatbot_tool_calls",             chatbot.get_tool_call_merge_query),
        ("AIArticle",           "dim_ai_articles",                    ai_art.get_ai_article_merge_query),
        ("News",                "dim_news",                           news.get_news_merge_query),
        # Economy
        ("CoinTransaction",     "fct_coin_transactions",              economy.get_coin_transaction_merge_query),
        ("Voucher",             "dim_voucher_catalog",                vouchers.get_voucher_merge_query),
        ("PartnerReward",       "dim_partner_reward_catalog",         partner_rewards.get_partner_reward_merge_query),
        ("PartnerReward",       "fct_partner_reward_inventory",       partner_rewards.get_partner_reward_enrichment_merge_query),
        ("SubscriptionProduct", "dim_subscription_products",          subscriptions.get_subscription_product_merge_query),
        ("FinancialEvent",      "fct_financial_events",               economy.get_financial_event_merge_query),
        # Competitions / gamification
        ("Duel",                "fct_prediction_duels",               duels.get_duel_merge_query),
        ("Super6Round",         "dim_super6_rounds",                  competitions.get_super6_round_merge_query),
        ("LMSCompetition",      "dim_lms_competitions",               competitions.get_lms_competition_merge_query),
        ("Poll",                "dim_fixture_polls",                  gamification.get_poll_merge_query),
        ("Question",            "dim_questions",                      gamification.get_question_merge_query),
        ("Question",            "dim_questions_enhanced",             gamification.get_question_enrichment_merge_query),
        ("Quiz",                "dim_quizzes",                        gamification.get_quiz_merge_query),
        ("QuizQuestion",        "dim_quiz_questions_enhanced",        gamification.get_quiz_question_merge_query),
        ("Achievement",         "fct_awards_and_achievements",        ach.get_achievement_merge_query),
        # Tags / ops / notifications / moderation
        ("Tag",                 "dim_tags",                           tags.get_tag_merge_query),
        ("NotificationContent", "dim_notification_content",          notifications.get_notification_content_merge_query),
        ("ModerationEvent",     "fct_moderation_events",              moderation.get_moderation_event_merge_query),
    ]:
        registry.register_node_query(label, source_name, query_fn(source_name))


def _register_rel_queries(registry: MergeQueryRegistry) -> None:
    """Register all relationship merge queries from domain modules."""
    from app.loaders.merge_queries import achievements as ach
    from app.loaders.merge_queries import activities
    from app.loaders.merge_queries import chat_social
    from app.loaders.merge_queries import competitions
    from app.loaders.merge_queries import discussions
    from app.loaders.merge_queries import duels
    from app.loaders.merge_queries import economy
    from app.loaders.merge_queries import fixtures
    from app.loaders.merge_queries import gamification
    from app.loaders.merge_queries import memberships
    from app.loaders.merge_queries import moderation
    from app.loaders.merge_queries import notifications
    from app.loaders.merge_queries import partner_rewards
    from app.loaders.merge_queries import personas
    from app.loaders.merge_queries import posts
    from app.loaders.merge_queries import predictions
    from app.loaders.merge_queries import private_leagues
    from app.loaders.merge_queries import rating_history
    from app.loaders.merge_queries import sentiment
    from app.loaders.merge_queries import subscriptions
    from app.loaders.merge_queries import tags
    from app.loaders.merge_queries import team_affinity
    from app.loaders.merge_queries import themes
    from app.loaders.merge_queries import topics
    from app.loaders.merge_queries import users
    from app.loaders.merge_queries import vouchers
    from app.loaders.merge_queries import app_identity

    # (rel_type, source_name, end_label_or_None)
    for rel_type, source_name, end_label, query_fn in [
        # Identity / avatar / badge
        ("EQUIPPED",            "dim_users",                        None,       app_identity.get_equipped_merge_query),
        ("AWARDED",             "fct_awards_and_achievements",      None,       ach.get_awarded_merge_query),
        ("FAVORS",              "dim_users",                        None,       app_identity.get_favors_merge_query),
        # Sports
        ("PLAYS_IN",            "dim_teams",                        None,       fixtures.get_plays_in_merge_query),
        ("HOME_TEAM",           "dim_fixtures",                     None,       fixtures.get_home_team_merge_query),
        ("AWAY_TEAM",           "dim_fixtures",                     None,       fixtures.get_away_team_merge_query),
        ("IN_LEAGUE",           "dim_fixtures",                     None,       fixtures.get_in_league_merge_query),
        ("PLAYED_IN",           "dim_fixtures",                     None,       fixtures.get_played_in_merge_query),
        # Private leagues
        ("MEMBER_OF",           "dim_private_league_members",       None,       memberships.get_member_of_merge_query),
        ("HAS_THEME",           "dim_private_league_themes",        None,       themes.get_has_theme_merge_query),
        ("PROMOTES",            "dim_influencer_leagues",           None,       private_leagues.get_promotes_merge_query),
        # Social
        ("POSTED",              "dim_posts",                        None,       posts.get_posted_merge_query),
        ("COMMENTED",           "dim_comments",                     None,       posts.get_commented_merge_query),
        ("REPLIES_TO",          "dim_comments",                     None,       posts.get_replies_to_merge_query),
        ("JOINED_DISCUSSION",   "fct_discussion_events",            None,       discussions.get_joined_discussion_merge_query),
        ("DIRECT_MESSAGE",      "dim_chat_direct_pairs",            None,       chat_social.get_direct_message_merge_query),
        # Predictions
        ("PREDICTED",           "fct_predictions",                  None,       predictions.get_predicted_merge_query),
        ("CHALLENGED",          "fct_prediction_duels",             None,       duels.get_challenged_merge_query),
        # Intelligence
        ("EXHIBITS",            "fct_user_behavior",                None,       personas.get_exhibits_merge_query),
        ("HAS_STATE",           "fct_user_behavior",                None,       personas.get_has_state_merge_query),
        ("CURRENT_STATE",       "fct_user_behavior",                None,       personas.get_current_state_merge_query),
        ("DISCUSSED",           "fct_topics",                       None,       topics.get_discussed_merge_query),
        ("EXPRESSED",           "fct_sentiment",                    None,       sentiment.get_expressed_merge_query),
        ("HAS_AFFINITY",        "fct_team_affinity",                None,       team_affinity.get_has_affinity_merge_query),
        ("HAS_RATING",          "fct_user_rating_history",          None,       rating_history.get_has_rating_merge_query),
        ("ABOUT",               "dim_prediction_discussions",       None,       discussions.get_about_merge_query),
        # Activities (LIKED targets multiple end labels)
        ("LIKED",               "fct_user_activities",              "Post",     activities.get_liked_post_merge_query),
        ("LIKED",               "fct_user_activities",              "Comment",  activities.get_liked_comment_merge_query),
        ("ANSWERED",            "fct_user_activities",              None,       activities.get_answered_merge_query),
        ("FRIENDED",            "fct_user_activities",              None,       activities.get_friended_merge_query),
        # Competitions
        ("PARTICIPATED_IN",     "fct_super6_participants",          None,       competitions.get_participated_in_super6_merge_query),
        ("PARTICIPATED_IN",     "dim_lms_competitions",             None,       competitions.get_participated_in_lms_merge_query),
        ("HAS_FIXTURE",         "dim_super6_round_fixtures",        None,       competitions.get_has_fixture_merge_query),
        # Economy
        ("SPENT",               "fct_coin_transactions",            None,       economy.get_spent_merge_query),
        ("PURCHASED",           "fct_voucher_purchases",            None,       vouchers.get_purchased_merge_query),
        ("REDEEMED",            "fct_partner_reward_redemptions",   None,       partner_rewards.get_redeemed_merge_query),
        ("SUBSCRIBED_TO",       "fct_subscription_lifecycle",       None,       subscriptions.get_subscribed_to_merge_query),
        ("ACHIEVED",            "fct_awards_and_achievements",      None,       ach.get_achieved_merge_query),
        # Tags
        ("HAS_TAG",             "dim_posts",                        None,       tags.get_post_has_tag_merge_query),
        ("HAS_TAG",             "dim_news",                         None,       tags.get_news_has_tag_merge_query),
        ("HAS_TAG",             "dim_ai_articles",                  None,       tags.get_ai_article_has_tag_merge_query),
        # Notifications / moderation
        ("RECEIVED_NOTIFICATION","jct_notification_recipients",     None,       notifications.get_received_notification_merge_query),
        ("MODERATED",           "fct_moderation_events",            None,       moderation.get_moderated_merge_query),
        # AI / chatbot
        ("TALKED_TO",           "dim_chatbot_conversations",        None,       chat_social.get_talked_to_merge_query),
        ("HAS_MESSAGE",         "fct_chatbot_messages",             None,       chat_social.get_has_message_merge_query),
        ("USED_TOOL",           "fct_chatbot_tool_calls",           None,       chat_social.get_used_tool_merge_query),
        ("GENERATED_FOR",       "dim_ai_articles",                  None,       chat_social.get_generated_for_merge_query),
    ]:
        registry.register_rel_query(rel_type, source_name, query_fn(source_name), end_label)


class NodeLoader(BaseLoader):
    """
    Loads NodeRecord instances from a GraphWriteBatch into Neo4j.

    Groups NodeRecords by (label, source_name), looks up the merge query
    from the registry, and delegates to BatchWriter.
    """

    def __init__(
        self,
        neo4j_client: Neo4jClient,
        run_id: str,
        merge_query_registry: MergeQueryRegistry,
        batch_size: int = DEFAULT_BATCH_SIZE,
        dry_run: bool = False,
    ) -> None:
        super().__init__(neo4j_client, run_id, dry_run)
        self._registry = merge_query_registry
        self._writer = BatchWriter(
            neo4j_client=neo4j_client,
            run_id=run_id,
            batch_size=batch_size,
            dry_run=dry_run,
        )

    def load(self, batch: GraphWriteBatch) -> LoadResult:
        """
        Load all NodeRecord instances from a GraphWriteBatch into Neo4j.

        Validates the batch, groups by (label, source_name), looks up queries,
        and delegates writes to BatchWriter.
        """
        started = perf_counter()
        result = LoadResult(source_name=batch.source_name, run_id=self._run_id)

        log_load_started(
            self._logger,
            run_id=self._run_id,
            batch_id=batch.batch_id,
            source_name=batch.source_name,
            node_count=batch.node_count(),
        )

        # Pre-load validation
        validation_results = validate_graph_write_batch(batch, self._run_id)
        critical_or_error = [
            r for r in validation_results if r.severity in ("CRITICAL", "ERROR") and not r.passed
        ]
        if critical_or_error:
            error_msgs = [r.message for r in critical_or_error]
            result.errors.extend(error_msgs)
            result.duration_seconds = self._elapsed(started)
            log_event(
                self._logger,
                event_name="node_loader_validation_failed",
                message="Batch validation failed; aborting node load",
                error_count=len(error_msgs),
                batch_id=batch.batch_id,
            )
            return result

        if not batch.node_records:
            result.duration_seconds = self._elapsed(started)
            return result

        # Group by (label, source_name)
        groups: dict[tuple[str, str], list[NodeRecord]] = defaultdict(list)
        for rec in batch.node_records:
            groups[(rec.label, rec.source_name)].append(rec)

        for (label, source_name), records in groups.items():
            written, skipped = self.load_nodes_for_label(label, source_name, records)
            result.nodes_written += written
            result.nodes_skipped += skipped
            result.batch_count += 1

        result.duration_seconds = self._elapsed(started)

        log_load_finished(
            self._logger,
            run_id=self._run_id,
            batch_id=batch.batch_id,
            record_count=result.nodes_written,
            duration_ms=int(result.duration_seconds * 1000),
            source_name=batch.source_name,
        )
        return result

    def load_nodes_for_label(
        self,
        label: str,
        source_name: str,
        records: list[NodeRecord],
    ) -> tuple[int, int]:
        """
        Load nodes for a single (label, source_name) combination.

        Returns (written_count, skipped_count).
        """
        query = self._registry.get_node_query(label, source_name)
        if query is None:
            log_event(
                self._logger,
                event_name="node_query_not_found",
                message=f"No merge query registered for ({label}, {source_name}) — records skipped",
                label=label,
                source_name=source_name,
                record_count=len(records),
            )
            return 0, len(records)

        try:
            written, skipped = self._writer.write_nodes(query, records)
            log_event(
                self._logger,
                event_name="nodes_written",
                message=f"Wrote {written} {label} nodes from {source_name}",
                label=label,
                source_name=source_name,
                written=written,
                skipped=skipped,
            )
            return written, skipped
        except Exception as exc:
            log_event(
                self._logger,
                event_name="node_write_error",
                message=f"Error writing {label} nodes from {source_name}",
                label=label,
                source_name=source_name,
                error=str(exc),
            )
            raise
