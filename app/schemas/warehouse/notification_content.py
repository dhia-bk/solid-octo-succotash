"""
Warehouse schema for dim_notification_content.

Source table: dim_notification_content
Domain: engagement
Inclusion mode: GRAPH_CORE — direct graph node creation
Graph entity: NotificationContent
Freshness field: last_seen_at_utc

Deduplicated notification message catalog. Feeds NotificationContent nodes
and RECEIVED_NOTIFICATION relationship (User → NotificationContent).

DWH type notes:
    content_id          — VARCHAR(100); no declared PK constraint; str.
    first/last_seen_date_key — INTEGER partition keys; str | None.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.core.constants import GRAPH_CORE, NOTIFICATION_CONTENT
from app.core.ids import normalize_nullable_string_id, normalize_string_id
from app.core.time import warehouse_value_to_utc_datetime

# ── Module-level constants ────────────────────────────────────────────────────

SOURCE_NAME: str = "dim_notification_content"
INCLUSION_MODE: str = GRAPH_CORE
PRIMARY_KEYS: tuple[str, ...] = ("content_id",)
FRESHNESS_FIELD: str | None = "last_seen_at_utc"
GRAPH_ENTITY_MAPPINGS: tuple[str, ...] = (NOTIFICATION_CONTENT,)


# ── Row shape ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class NotificationContentRow:
    """
    Typed row shape for dim_notification_content.

    content_id is VARCHAR(100) with no PK constraint; treated as the stable
    de facto key.
    first_seen_date_key and last_seen_date_key are INTEGER partition keys;
    str | None.
    """

    content_id: str
    sender_user_id: str | None
    normalized_message_text: str | None
    message_text_sample: str | None
    first_seen_at_utc: datetime | None
    last_seen_at_utc: datetime | None
    first_seen_date_key: str | None
    last_seen_date_key: str | None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> NotificationContentRow:
        """Normalize a raw warehouse row into a typed NotificationContentRow."""
        return cls(
            content_id=normalize_string_id(row["content_id"], field_name="content_id"),
            sender_user_id=normalize_nullable_string_id(row.get("sender_user_id"), field_name="sender_user_id"),
            normalized_message_text=row.get("normalized_message_text"),
            message_text_sample=row.get("message_text_sample"),
            first_seen_at_utc=warehouse_value_to_utc_datetime(row.get("first_seen_at_utc")),
            last_seen_at_utc=warehouse_value_to_utc_datetime(row.get("last_seen_at_utc")),
            first_seen_date_key=str(row["first_seen_date_key"]) if row.get("first_seen_date_key") is not None else None,
            last_seen_date_key=str(row["last_seen_date_key"]) if row.get("last_seen_date_key") is not None else None,
        )
