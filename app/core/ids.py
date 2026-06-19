"""
Canonical ID utilities for Project Pulse Knowledge Graph.

Design rules:
- All normalized IDs are string-based.
- All normalization is deterministic and stable.
- Empty values are rejected unless an explicit nullable helper is used.
- Composite keys must have a stable field order.
- No later module should invent IDs inline if a helper exists here.
"""

from __future__ import annotations

import hashlib
import re
from decimal import Decimal
from typing import Any

from app.core.exceptions import ValidationError

# ============================================================================
# Primitive normalization helpers
# ============================================================================

_WHITESPACE_RE = re.compile(r"\s+")
_SLUG_INVALID_RE = re.compile(r"[^a-z0-9]+")
_SAFE_KEY_PART_SEPARATOR = "::"


def _stringify_primitive(value: Any) -> str:
    """
    Convert a primitive value into a stable string form.

    Supported types:
    - str
    - int
    - float
    - Decimal
    - bool

    Returns:
        Stable string representation.

    Raises:
        ValidationError: If the value type is unsupported.
    """
    if isinstance(value, str):
        return value

    if isinstance(value, bool):
        return "true" if value else "false"

    if isinstance(value, int):
        return str(value)

    if isinstance(value, Decimal):
        return format(value.normalize(), "f")

    if isinstance(value, float):
        # Stable enough for IDs only when source values are already discrete.
        return format(value, ".15g")

    raise ValidationError(
        "Unsupported ID value type",
        raw_type=type(value).__name__,
        raw_value=repr(value),
    )


def normalize_string_id(value: Any, *, field_name: str = "id") -> str:
    """
    Normalize an ID-like value into a canonical non-empty string.

    Rules:
    - strings are stripped
    - internal repeated whitespace is collapsed to a single space
    - ints / floats / decimals / bools are stringified
    - empty strings are rejected

    Args:
        value: Raw ID value.
        field_name: Logical field name for error context.

    Returns:
        Canonical non-empty string.

    Raises:
        ValidationError: If value is null, blank, or unsupported.
    """
    if value is None:
        raise ValidationError(
            "ID value cannot be null",
            field_name=field_name,
        )

    text = _stringify_primitive(value)
    text = text.strip()
    text = _WHITESPACE_RE.sub(" ", text)

    if not text:
        raise ValidationError(
            "ID value cannot be empty",
            field_name=field_name,
            raw_value=repr(value),
        )

    return text


def normalize_nullable_string_id(value: Any, *, field_name: str = "id") -> str | None:
    """
    Normalize an optional ID-like value into a canonical string or None.

    Args:
        value: Raw ID value.
        field_name: Logical field name for error context.

    Returns:
        Canonical string or None.
    """
    if value is None:
        return None

    if isinstance(value, str) and not value.strip():
        return None

    return normalize_string_id(value, field_name=field_name)


def trim_and_collapse_whitespace(value: str) -> str:
    """
    Strip leading/trailing whitespace and collapse repeated internal whitespace.

    Args:
        value: Raw string.

    Returns:
        Cleaned string.
    """
    return _WHITESPACE_RE.sub(" ", value.strip())


def require_non_empty(value: str, *, field_name: str) -> str:
    """
    Ensure a string is non-empty after trimming.

    Args:
        value: Input string.
        field_name: Logical field name.

    Returns:
        Cleaned non-empty string.
    """
    cleaned = trim_and_collapse_whitespace(value)
    if not cleaned:
        raise ValidationError(
            "Value cannot be empty",
            field_name=field_name,
        )
    return cleaned


# ============================================================================
# Stable slug helpers
# ============================================================================


def slugify(value: Any, *, field_name: str = "value", max_length: int | None = 120) -> str:
    """
    Convert a value into a deterministic lowercase slug.

    Rules:
    - normalize to canonical string
    - lowercase
    - replace non-alphanumeric runs with single hyphen
    - strip leading/trailing hyphens
    - optionally truncate

    Args:
        value: Input value.
        field_name: Logical field name.
        max_length: Optional maximum slug length.

    Returns:
        Stable slug string.
    """
    text = normalize_string_id(value, field_name=field_name).lower()
    slug = _SLUG_INVALID_RE.sub("-", text).strip("-")

    if not slug:
        raise ValidationError(
            "Slugified value cannot be empty",
            field_name=field_name,
            raw_value=repr(value),
        )

    if max_length is not None:
        slug = slug[:max_length].rstrip("-")

    return slug


def stable_hash_key(*parts: Any, length: int = 16) -> str:
    """
    Build a deterministic short hash from ordered key parts.

    Args:
        *parts: Ordered values.
        length: Length of returned hex digest prefix.

    Returns:
        Deterministic lowercase hex string.
    """
    canonical = "|".join(normalize_string_id(part, field_name="hash_part") for part in parts)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return digest[:length]


# ============================================================================
# Entity-specific ID builders
# ============================================================================


def build_user_id(user_id: Any) -> str:
    """Build canonical User ID."""
    return normalize_string_id(user_id, field_name="user_id")


def build_team_id(team_id: Any) -> str:
    """Build canonical Team ID."""
    return normalize_string_id(team_id, field_name="team_id")


def build_fixture_id(fixture_id: Any) -> str:
    """Build canonical Match/Fixture ID."""
    return normalize_string_id(fixture_id, field_name="fixture_id")


def build_league_id(league_id: Any) -> str:
    """Build canonical League ID."""
    return normalize_string_id(league_id, field_name="league_id")


def build_private_league_id(private_league_id: Any) -> str:
    """Build canonical PrivateLeague ID."""
    return normalize_string_id(private_league_id, field_name="private_league_id")


def build_post_id(post_id: Any) -> str:
    """Build canonical Post ID."""
    return normalize_string_id(post_id, field_name="post_id")


def build_comment_id(comment_id: Any) -> str:
    """Build canonical Comment ID."""
    return normalize_string_id(comment_id, field_name="comment_id")


def build_discussion_id(discussion_id: Any) -> str:
    """Build canonical Discussion ID."""
    return normalize_string_id(discussion_id, field_name="discussion_id")


def build_prediction_id(prediction_id: Any) -> str:
    """Build canonical Prediction ID."""
    return normalize_string_id(prediction_id, field_name="prediction_id")


def build_duel_id(duel_id: Any) -> str:
    """Build canonical Duel ID."""
    return normalize_string_id(duel_id, field_name="duel_id")


def build_super6_round_id(super6_round_id: Any) -> str:
    """Build canonical Super6Round ID."""
    return normalize_string_id(super6_round_id, field_name="super6_round_id")


def build_lms_competition_id(lms_competition_id: Any) -> str:
    """Build canonical LMSCompetition ID."""
    return normalize_string_id(lms_competition_id, field_name="lms_competition_id")


def build_voucher_id(voucher_id: Any) -> str:
    """Build canonical Voucher ID."""
    return normalize_string_id(voucher_id, field_name="voucher_id")


def build_reward_id(reward_id: Any) -> str:
    """Build canonical PartnerReward ID."""
    return normalize_string_id(reward_id, field_name="reward_id")


def build_topic_id(topic_id: Any) -> str:
    """Build canonical Topic ID."""
    return normalize_string_id(topic_id, field_name="topic_id")


def build_sentiment_id(sentiment_id: Any) -> str:
    """Build canonical Sentiment ID."""
    return normalize_string_id(sentiment_id, field_name="sentiment_id")


def build_persona_state_id(persona_state_id: Any) -> str:
    """Build canonical PersonaState ID."""
    return normalize_string_id(persona_state_id, field_name="persona_state_id")


def build_chatbot_conversation_id(conversation_id: Any) -> str:
    """Build canonical ChatbotConversation ID."""
    return normalize_string_id(conversation_id, field_name="chatbot_conversation_id")


def build_chatbot_message_id(message_id: Any) -> str:
    """Build canonical ChatbotMessage ID."""
    return normalize_string_id(message_id, field_name="chatbot_message_id")


def build_tool_call_id(tool_call_id: Any) -> str:
    """Build canonical ToolCall ID."""
    return normalize_string_id(tool_call_id, field_name="tool_call_id")


def build_news_id(news_id: Any) -> str:
    """Build canonical News ID."""
    return normalize_string_id(news_id, field_name="news_id")


def build_ai_article_id(article_id: Any) -> str:
    """Build canonical AIArticle ID."""
    return normalize_string_id(article_id, field_name="article_id")


def build_quiz_id(quiz_id: Any) -> str:
    """Build canonical Quiz ID."""
    return normalize_string_id(quiz_id, field_name="quiz_id")


def build_quiz_question_id(quiz_question_id: Any) -> str:
    """Build canonical QuizQuestion ID."""
    return normalize_string_id(quiz_question_id, field_name="quiz_question_id")


def build_question_id(question_id: Any) -> str:
    """Build canonical Question ID."""
    return normalize_string_id(question_id, field_name="question_id")


def build_poll_id(poll_id: Any) -> str:
    """Build canonical Poll ID."""
    return normalize_string_id(poll_id, field_name="poll_id")


def build_tag_id(tag_id: Any) -> str:
    """Build canonical Tag ID."""
    return normalize_string_id(tag_id, field_name="tag_id")


def build_notification_content_id(content_id: Any) -> str:
    """Build canonical NotificationContent ID."""
    return normalize_string_id(content_id, field_name="content_id")


def build_moderation_event_id(event_id: Any) -> str:
    """Build canonical ModerationEvent ID."""
    return normalize_string_id(event_id, field_name="moderation_event_id")


def build_achievement_id(achievement_id: Any) -> str:
    """Build canonical Achievement ID."""
    return normalize_string_id(achievement_id, field_name="achievement_id")


def build_avatar_id(avatar_id: Any) -> str:
    """Build canonical Avatar ID."""
    return normalize_string_id(avatar_id, field_name="avatar_id")


def build_badge_id(badge_id: Any) -> str:
    """Build canonical Badge ID."""
    return normalize_string_id(badge_id, field_name="badge_id")


# ============================================================================
# Composite key builders
# ============================================================================


def _compose_key(*parts: str) -> str:
    """
    Join normalized parts into a stable composite key.

    Uses a reserved separator to avoid ambiguity.
    """
    return _SAFE_KEY_PART_SEPARATOR.join(parts)


def build_membership_key(user_id: Any, private_league_id: Any) -> str:
    """
    Build a stable membership key for User -> MEMBER_OF -> PrivateLeague.
    """
    return _compose_key(
        "membership",
        build_user_id(user_id),
        build_private_league_id(private_league_id),
    )


def build_notification_recipient_key(notification_id: Any, user_id: Any) -> str:
    """
    Build a stable key for a notification recipient record.
    """
    return _compose_key(
        "notification_recipient",
        normalize_string_id(notification_id, field_name="notification_id"),
        build_user_id(user_id),
    )


def build_quiz_question_membership_key(quiz_id: Any, quiz_question_id: Any) -> str:
    """
    Build a stable key for Quiz -> HAS_QUESTION -> QuizQuestion.
    """
    return _compose_key(
        "quiz_question",
        build_quiz_id(quiz_id),
        build_quiz_question_id(quiz_question_id),
    )


def build_persona_state_snapshot_key(
    user_id: Any,
    state_label: Any,
    calculated_at: Any,
) -> str:
    """
    Build a stable synthetic key for a persona state snapshot.

    This is useful when the source does not provide a perfect immutable key for
    the logical user-state-at-time record.
    """
    return _compose_key(
        "persona_state_snapshot",
        build_user_id(user_id),
        slugify(state_label, field_name="state_label"),
        normalize_string_id(calculated_at, field_name="calculated_at"),
    )


def build_inferred_label_key(
    user_id: Any,
    label_type: Any,
    label_value: Any,
    model_version: Any,
    run_id: Any,
) -> str:
    """
    Build a stable key for an inferred label artifact.
    """
    return _compose_key(
        "inferred_label",
        build_user_id(user_id),
        slugify(label_type, field_name="label_type"),
        slugify(label_value, field_name="label_value"),
        normalize_string_id(model_version, field_name="model_version"),
        normalize_string_id(run_id, field_name="run_id"),
    )


def build_direct_pair_key(user_a_id: Any, user_b_id: Any) -> str:
    """
    Build a stable canonical user-user pair key.

    Ordering is normalized so A-B and B-A generate the same key.
    """
    left = build_user_id(user_a_id)
    right = build_user_id(user_b_id)
    ordered = sorted((left, right))
    return _compose_key("direct_pair", ordered[0], ordered[1])


def build_discussion_membership_key(user_id: Any, discussion_id: Any) -> str:
    """
    Build a stable key for User -> JOINED_DISCUSSION -> Discussion.
    """
    return _compose_key(
        "discussion_membership",
        build_user_id(user_id),
        build_discussion_id(discussion_id),
    )


def build_prediction_edge_key(user_id: Any, fixture_id: Any, prediction_id: Any) -> str:
    """
    Build a stable key for User -> PREDICTED -> Match edge records.
    """
    return _compose_key(
        "prediction_edge",
        build_user_id(user_id),
        build_fixture_id(fixture_id),
        build_prediction_id(prediction_id),
    )


def build_tag_assignment_key(owner_type: Any, owner_id: Any, tag_id: Any) -> str:
    """
    Build a stable key for content/tag assignment.
    """
    return _compose_key(
        "tag_assignment",
        slugify(owner_type, field_name="owner_type"),
        normalize_string_id(owner_id, field_name="owner_id"),
        build_tag_id(tag_id),
    )


def build_tool_usage_key(message_id: Any, tool_call_id: Any) -> str:
    """
    Build a stable key for ChatbotMessage -> USED_TOOL -> ToolCall.
    """
    return _compose_key(
        "tool_usage",
        build_chatbot_message_id(message_id),
        build_tool_call_id(tool_call_id),
    )


# ============================================================================
# Stable public/serving identifiers
# ============================================================================


def build_public_slug(prefix: str, raw_value: Any) -> str:
    """
    Build a stable prefixed serving/public slug.

    Example:
        user: 'user-john-doe'
        tribe: 'tribe-42'
    """
    prefix_clean = slugify(prefix, field_name="prefix", max_length=40)
    value_clean = slugify(raw_value, field_name="raw_value", max_length=120)
    return f"{prefix_clean}-{value_clean}"


def build_compact_hash_id(prefix: str, *parts: Any, length: int = 16) -> str:
    """
    Build a short deterministic identifier with a readable prefix.

    Example:
        inferred-4c0dbe12aa77e4b2
    """
    prefix_clean = slugify(prefix, field_name="prefix", max_length=40)
    digest = stable_hash_key(*parts, length=length)
    return f"{prefix_clean}-{digest}"
