"""
Warehouse schema for dim_users.

Source table: dim_users
Domain: identity
Inclusion mode: GRAPH_CORE — direct graph node creation
Graph entity: User
Freshness field: last_activity_at_utc

This is the primary identity source for the platform. Every user-centric
edge in the graph originates from a User node backed by this table.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.core.constants import GRAPH_CORE, USER
from app.core.ids import normalize_nullable_string_id, normalize_string_id
from app.core.time import warehouse_value_to_utc_datetime

# ── Module-level constants ────────────────────────────────────────────────────

SOURCE_NAME: str = "dim_users"
INCLUSION_MODE: str = GRAPH_CORE
PRIMARY_KEYS: tuple[str, ...] = ("user_id",)
FRESHNESS_FIELD: str | None = "last_activity_at_utc"
GRAPH_ENTITY_MAPPINGS: tuple[str, ...] = (USER,)


# ── Row shape ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class UsersRow:
    """
    Typed row shape for dim_users.

    TINYINT fields (0/1 integers, not booleans in the DWH):
        has_early_prediction_permission
        is_suspended
        is_waiting
        lockout_enabled

    Type overrides vs raw DWH type:
        duel_rating    — DWH stores INTEGER, exposed as float (conceptually
                         a continuous ELO-style rating that gains decimal
                         precision as the platform evolves).
        avatar_id      — DWH stores INTEGER, kept as int | None (not a
                         graph-level string ID at this schema layer).
        birthdate      — DWH stores DATE, kept as str | None (date-only
                         string; not converted to datetime to avoid spurious
                         timezone shifts on date-only values).
    """

    user_id: str
    user_name: str | None
    full_name: str | None
    country: str | None
    birthdate: str | None
    age: int | None
    user_created_at_utc: datetime | None
    gender: str | None
    favorite_team_id: str | None
    favorite_team_name: str | None
    first_activity_at_utc: datetime | None
    last_activity_at_utc: datetime | None
    lifetime_posts: int | None
    lifetime_comments: int | None
    lifetime_predictions: int | None
    lifetime_prediction_points: int | None
    current_streak_count: int | None
    longest_streak_count: int | None
    current_subscription_name: str | None
    has_early_prediction_permission: int | None
    is_suspended: int | None
    referred_by_user_id: str | None
    referral_code: str | None
    is_waiting: int | None
    lockout_enabled: int | None
    lockout_end_utc: datetime | None
    access_failed_count: int | None
    days_since_last_activity: int | None
    blocks_given_count: int | None
    blocks_received_count: int | None
    ai_total_credits: int | None
    ai_remaining_credits: int | None
    ai_credits_expires_at_utc: datetime | None
    ai_credits_last_reset_at_utc: datetime | None
    last_payment_at_utc: datetime | None
    days_since_last_payment: int | None
    avatar_category: str | None
    avatar_id: int | None
    auth_provider: str | None
    all_auth_providers: str | None  # comma-separated or JSON string in DWH
    duel_rating: float | None
    notif_total_received: int | None
    notif_total_read: int | None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> UsersRow:
        """Normalize a raw warehouse row into a typed UsersRow."""
        return cls(
            user_id=normalize_string_id(row["user_id"], field_name="user_id"),
            user_name=row.get("user_name"),
            full_name=row.get("full_name"),
            country=row.get("country"),
            birthdate=str(row["birthdate"]) if row.get("birthdate") is not None else None,
            age=int(row["age"]) if row.get("age") is not None else None,
            user_created_at_utc=warehouse_value_to_utc_datetime(row.get("user_created_at_utc")),
            gender=row.get("gender"),
            favorite_team_id=normalize_nullable_string_id(
                row.get("favorite_team_id"), field_name="favorite_team_id"
            ),
            favorite_team_name=row.get("favorite_team_name"),
            first_activity_at_utc=warehouse_value_to_utc_datetime(row.get("first_activity_at_utc")),
            last_activity_at_utc=warehouse_value_to_utc_datetime(row.get("last_activity_at_utc")),
            lifetime_posts=int(row["lifetime_posts"]) if row.get("lifetime_posts") is not None else None,
            lifetime_comments=int(row["lifetime_comments"]) if row.get("lifetime_comments") is not None else None,
            lifetime_predictions=int(row["lifetime_predictions"]) if row.get("lifetime_predictions") is not None else None,
            lifetime_prediction_points=int(row["lifetime_prediction_points"]) if row.get("lifetime_prediction_points") is not None else None,
            current_streak_count=int(row["current_streak_count"]) if row.get("current_streak_count") is not None else None,
            longest_streak_count=int(row["longest_streak_count"]) if row.get("longest_streak_count") is not None else None,
            current_subscription_name=row.get("current_subscription_name"),
            has_early_prediction_permission=int(row["has_early_prediction_permission"]) if row.get("has_early_prediction_permission") is not None else None,
            is_suspended=int(row["is_suspended"]) if row.get("is_suspended") is not None else None,
            referred_by_user_id=normalize_nullable_string_id(
                row.get("referred_by_user_id"), field_name="referred_by_user_id"
            ),
            referral_code=row.get("referral_code"),
            is_waiting=int(row["is_waiting"]) if row.get("is_waiting") is not None else None,
            lockout_enabled=int(row["lockout_enabled"]) if row.get("lockout_enabled") is not None else None,
            lockout_end_utc=warehouse_value_to_utc_datetime(row.get("lockout_end_utc")),
            access_failed_count=int(row["access_failed_count"]) if row.get("access_failed_count") is not None else None,
            days_since_last_activity=int(row["days_since_last_activity"]) if row.get("days_since_last_activity") is not None else None,
            blocks_given_count=int(row["blocks_given_count"]) if row.get("blocks_given_count") is not None else None,
            blocks_received_count=int(row["blocks_received_count"]) if row.get("blocks_received_count") is not None else None,
            ai_total_credits=int(row["ai_total_credits"]) if row.get("ai_total_credits") is not None else None,
            ai_remaining_credits=int(row["ai_remaining_credits"]) if row.get("ai_remaining_credits") is not None else None,
            ai_credits_expires_at_utc=warehouse_value_to_utc_datetime(row.get("ai_credits_expires_at_utc")),
            ai_credits_last_reset_at_utc=warehouse_value_to_utc_datetime(row.get("ai_credits_last_reset_at_utc")),
            last_payment_at_utc=warehouse_value_to_utc_datetime(row.get("last_payment_at_utc")),
            days_since_last_payment=int(row["days_since_last_payment"]) if row.get("days_since_last_payment") is not None else None,
            avatar_category=row.get("avatar_category"),
            avatar_id=int(row["avatar_id"]) if row.get("avatar_id") is not None else None,
            auth_provider=row.get("auth_provider"),
            all_auth_providers=row.get("all_auth_providers"),
            duel_rating=float(row["duel_rating"]) if row.get("duel_rating") is not None else None,
            notif_total_received=int(row["notif_total_received"]) if row.get("notif_total_received") is not None else None,
            notif_total_read=int(row["notif_total_read"]) if row.get("notif_total_read") is not None else None,
        )
