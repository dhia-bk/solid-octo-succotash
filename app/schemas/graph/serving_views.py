"""
Serving view contracts for Project Pulse Knowledge Graph.

These are typed payload shapes produced by the app/loaders/serving/ layer
and consumed by the service layer. They are not Neo4j views — they are
stable, versioned data structures that represent the final output of the
graph + analytics pipeline for downstream product consumption.

Each view aggregates fields from multiple graph nodes and analytics outputs
into a single flat or lightly nested shape. Serving views are the boundary
between the graph infrastructure and the API / notification / ML serving layers.

Design rules:
- All fields use Python native types, not graph or warehouse types.
- Timestamps are str | None (ISO 8601).
- Lists default to empty list, not None — consumers should not need to
  null-check list fields.
- Each view is immutable (frozen=True).
- The SERVING_VIEW_REGISTRY maps stable string keys to view classes for
  use by the materialization loader and serving health checks.
"""

from __future__ import annotations

from dataclasses import dataclass, field


# ============================================================================
# User profile view
# ============================================================================


@dataclass(frozen=True)
class UserProfileView:
    """
    Flattened user profile for the API and persona service layer.

    Sources:
        User node          — identity, demographics, subscription, credits
        PersonaState node  — current_pcm_stage, behaviour_label (via CURRENT_STATE)
        Analytics          — tribe_id (Leiden), pagerank_score (PageRank)
        dim_users          — lifetime_predictions, lifetime_posts

    Consumed by: user_profile_service.py

    tribe_id and pagerank_score are null until the first analytics run
    completes after initial graph load.
    """

    user_id: str
    user_name: str | None
    country: str | None
    gender: str | None
    age: int | None
    favorite_team_id: str | None
    current_subscription_name: str | None
    duel_rating: float | None
    tribe_id: str | None
    pagerank_score: float | None
    current_pcm_stage: str | None
    behaviour_label: str | None
    lifetime_predictions: int | None
    lifetime_posts: int | None
    ai_remaining_credits: int | None


# ============================================================================
# Tribe summary view
# ============================================================================


@dataclass(frozen=True)
class TribeSummaryView:
    """
    Aggregated tribe summary for the tribe service layer.

    Sources:
        Leiden community detection output   — tribe_id, cohesion_score
        User nodes within tribe             — member_count, avg_duel_rating
        PageRank scores                     — avg_pagerank
        HAS_AFFINITY edges                  — top_teams
        Topic nodes                         — top_topics
        League nodes                        — top_leagues
        PersonaState nodes                  — dominant_pcm_stage

    Consumed by: tribe_service.py

    List fields default to empty list. A tribe with no top_teams has not
    yet had affinity signals materialized, which is distinct from a tribe
    with null top_teams (which should not occur).
    """

    tribe_id: str
    member_count: int
    top_teams: list[str] = field(default_factory=list)
    top_topics: list[str] = field(default_factory=list)
    top_leagues: list[str] = field(default_factory=list)
    avg_pagerank: float | None = None
    avg_duel_rating: float | None = None
    dominant_pcm_stage: str | None = None
    cohesion_score: float | None = None


# ============================================================================
# Inference result view
# ============================================================================


@dataclass(frozen=True)
class InferenceResultView:
    """
    Single inference output record for a user.

    Sources:
        Inference pipeline output   — inferred_tribe_id, confidence_score,
                                      inference_run_id, model_version, inferred_at
        User node                   — user_id

    Consumed by: inference_service.py

    label_type identifies what the inference is predicting. Currently
    "tribe_assignment" is the only active label type, but the field is
    kept explicit to support future inference targets (e.g. churn_risk,
    content_preference) without schema changes.

    inferred_at is an ISO 8601 timestamp string.
    """

    user_id: str
    inferred_tribe_id: str | None
    confidence_score: float | None
    inference_run_id: str
    model_version: str
    inferred_at: str
    label_type: str


# ============================================================================
# Notification feature view
# ============================================================================


@dataclass(frozen=True)
class NotificationFeatureView:
    """
    Per-user notification feature payload for the notification service.

    Sources:
        fct_user_notification_stats     — read_rate_pct, consistency_score,
                                          last_notification_at
        Topic nodes (DISCUSSED edges)   — preferred_topics
        Sentiment nodes (EXPRESSED)     — dominant_sentiment
        fct_user_sessions               — active_hours (hour-of-day buckets)

    Consumed by: notification_service.py

    preferred_topics and active_hours default to empty list/None.
    active_hours is a list of integer hour-of-day values (0–23) that
    represent when the user is most likely to engage.
    last_notification_at is an ISO 8601 timestamp string or None.
    """

    user_id: str
    read_rate_pct: float | None
    consistency_score: float | None
    preferred_topics: list[str] = field(default_factory=list)
    dominant_sentiment: str | None = None
    active_hours: list[int] | None = None
    last_notification_at: str | None = None


# ============================================================================
# Content feature view
# ============================================================================


@dataclass(frozen=True)
class ContentFeatureView:
    """
    Per-content feature payload for the content and recommendation service.

    Sources:
        Post / News / AIArticle node    — content_id, content_type,
                                          engagement_score
        Tag nodes (HAS_TAG edges)       — tag_ids
        Sentiment nodes                 — sentiment_label
        Topic nodes                     — topic_labels
        Tag node (is_trending)          — is_trending

    Consumed by: content_service.py

    content_type is one of: "Post", "News", "AIArticle"

    tag_ids and topic_labels default to empty list. engagement_score is
    a normalized float computed by the analytics feature pipeline over
    likes, comments, and views.
    """

    content_id: str
    content_type: str
    tag_ids: list[str] = field(default_factory=list)
    sentiment_label: str | None = None
    topic_labels: list[str] = field(default_factory=list)
    engagement_score: float | None = None
    is_trending: bool | None = None


# ============================================================================
# Serving view registry
# ============================================================================

SERVING_VIEW_REGISTRY: dict[str, type] = {
    "user_profile": UserProfileView,
    "tribe_summary": TribeSummaryView,
    "inference_result": InferenceResultView,
    "notification_feature": NotificationFeatureView,
    "content_feature": ContentFeatureView,
}