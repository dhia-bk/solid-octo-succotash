"""
Merge queries for User nodes and User enrichment.
Source(s): dim_users, dim_notification_preferences
"""

from __future__ import annotations

from app.loaders.merge_queries.base import (
    build_enrichment_merge_query,
    build_node_merge_query,
)


def get_user_merge_query(source_name: str = "dim_users") -> str:
    """Return Cypher MERGE query for User nodes from source_name."""
    return build_node_merge_query(
        label="User",
        merge_key_field="id",
        write_once_fields=["user_created_at", "first_activity_at"],
        mutable_fields=[
            "user_name",
            "full_name",
            "country",
            "gender",
            "age",
            "last_activity_at",
            "favorite_team_id",
            "favorite_team_name",
            "current_subscription_name",
            "duel_rating",
            "ai_total_credits",
            "ai_remaining_credits",
            "last_payment_at",
            "avatar_category",
            "avatar_id",
            "notif_total_received",
            "notif_total_read",
            "is_suspended",
        ],
    )


def get_user_enrichment_merge_query(source_name: str = "dim_notification_preferences") -> str:
    """Return Cypher MERGE query for User enrichment from source_name."""
    return build_enrichment_merge_query(
        label="User",
        merge_key_field="id",
        enrichment_fields=[],
        write_policy_overwrite=["notification_opt_in", "notification_channel_preferences"],
        write_policy_fill_if_null=[],
    )
