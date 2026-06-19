"""
Warehouse schema for jct_notification_recipients.

Source table: jct_notification_recipients
Domain: engagement
Inclusion mode: GRAPH_CORE — feeds relationship creation
Graph entity: RECEIVED_NOTIFICATION relationship (User → NotificationContent)
Freshness field: sent_at_utc

Junction table linking notifications to recipient users. No declared PK
constraint; composite key (notification_id, user_id) is the stable identifier.
Feeds RECEIVED_NOTIFICATION edge properties: sent_at, is_read, read_at.

DWH type notes:
    notification_date_key — INTEGER partition key; str | None.
    is_read               — TINYINT 0/1.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.core.constants import GRAPH_CORE, RECEIVED_NOTIFICATION
from app.core.ids import normalize_nullable_string_id, normalize_string_id
from app.core.time import warehouse_value_to_utc_datetime

# ── Module-level constants ────────────────────────────────────────────────────

SOURCE_NAME: str = "jct_notification_recipients"
INCLUSION_MODE: str = GRAPH_CORE
PRIMARY_KEYS: tuple[str, ...] = ("notification_id", "user_id")
FRESHNESS_FIELD: str | None = "sent_at_utc"
GRAPH_ENTITY_MAPPINGS: tuple[str, ...] = (RECEIVED_NOTIFICATION,)


# ── Row shape ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class NotificationRecipientsRow:
    """
    Typed row shape for jct_notification_recipients.

    TINYINT fields (0/1 integers, not booleans in the DWH):
        is_read

    No single-column PK declared in DWH. The composite key
    (notification_id, user_id) is the stable row identifier.
    notification_date_key is an INTEGER partition key; str | None.
    """

    notification_id: str
    user_id: str | None
    content_id: str | None
    notification_date_key: str | None
    sent_at_utc: datetime | None
    is_read: int | None
    read_at_utc: datetime | None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> NotificationRecipientsRow:
        """Normalize a raw warehouse row into a typed NotificationRecipientsRow."""
        return cls(
            notification_id=normalize_string_id(row["notification_id"], field_name="notification_id"),
            user_id=normalize_nullable_string_id(row.get("user_id"), field_name="user_id"),
            content_id=normalize_nullable_string_id(row.get("content_id"), field_name="content_id"),
            notification_date_key=str(row["notification_date_key"]) if row.get("notification_date_key") is not None else None,
            sent_at_utc=warehouse_value_to_utc_datetime(row.get("sent_at_utc")),
            is_read=int(row["is_read"]) if row.get("is_read") is not None else None,
            read_at_utc=warehouse_value_to_utc_datetime(row.get("read_at_utc")),
        )
