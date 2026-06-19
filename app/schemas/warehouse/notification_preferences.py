"""
Warehouse schema for dim_notification_preferences.

Source table: dim_notification_preferences
Domain: engagement
Inclusion mode: GRAPH_ENRICHMENT — enriches User nodes
Graph entity: User (enrichment; adds notification consent profile)
Freshness field: preference_updated_at_utc

Notification consent and device registration per user. One row per
(user_id, subscription_category) pair. The transformer must group by
user_id before writing enrichment properties to User nodes.

DWH type note:
    is_enabled — TINYINT 0/1.
    device_platforms — TEXT; comma-separated or JSON string.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.core.constants import GRAPH_ENRICHMENT, USER
from app.core.ids import normalize_string_id
from app.core.time import warehouse_value_to_utc_datetime

# ── Module-level constants ────────────────────────────────────────────────────

SOURCE_NAME: str = "dim_notification_preferences"
INCLUSION_MODE: str = GRAPH_ENRICHMENT
PRIMARY_KEYS: tuple[str, ...] = ("user_id",)
FRESHNESS_FIELD: str | None = "preference_updated_at_utc"
GRAPH_ENTITY_MAPPINGS: tuple[str, ...] = (USER,)


# ── Row shape ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class NotificationPreferencesRow:
    """
    Typed row shape for dim_notification_preferences.

    TINYINT fields (0/1 integers, not booleans in the DWH):
        is_enabled

    One row per (user_id, subscription_category). The transformer must
    group by user_id before writing enrichment properties to User nodes.
    device_platforms is a raw TEXT field (comma-separated or JSON string).
    """

    user_id: str
    subscription_category: str | None
    is_enabled: int | None
    preference_created_at_utc: datetime | None
    preference_updated_at_utc: datetime | None
    registered_device_count: int | None
    last_token_updated_at: datetime | None
    device_platforms: str | None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> NotificationPreferencesRow:
        """Normalize a raw warehouse row into a typed NotificationPreferencesRow."""
        return cls(
            user_id=normalize_string_id(row["user_id"], field_name="user_id"),
            subscription_category=row.get("subscription_category"),
            is_enabled=int(row["is_enabled"]) if row.get("is_enabled") is not None else None,
            preference_created_at_utc=warehouse_value_to_utc_datetime(row.get("preference_created_at_utc")),
            preference_updated_at_utc=warehouse_value_to_utc_datetime(row.get("preference_updated_at_utc")),
            registered_device_count=int(row["registered_device_count"]) if row.get("registered_device_count") is not None else None,
            last_token_updated_at=warehouse_value_to_utc_datetime(row.get("last_token_updated_at")),
            device_platforms=row.get("device_platforms"),
        )
