"""
Warehouse schema for fct_notification_content_daily.

Source table: fct_notification_content_daily
Domain: engagement
Inclusion mode: FEATURE_SOURCE — feeds notification scoring model only
Graph entity: none
Freshness field: first_sent_at_utc

Daily delivery aggregates per notification content item. No declared PK
constraint; content_day_id treated as the stable de facto key.

DWH type notes:
    notification_date_key — INTEGER partition key; str | None.
    read_rate_pct         — DECIMAL(5,2); float | None.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.core.constants import FEATURE_SOURCE
from app.core.ids import normalize_nullable_string_id, normalize_string_id
from app.core.time import warehouse_value_to_utc_datetime

# ── Module-level constants ────────────────────────────────────────────────────

SOURCE_NAME: str = "fct_notification_content_daily"
INCLUSION_MODE: str = FEATURE_SOURCE
PRIMARY_KEYS: tuple[str, ...] = ("content_day_id",)
FRESHNESS_FIELD: str | None = "first_sent_at_utc"
GRAPH_ENTITY_MAPPINGS: tuple[str, ...] = ()


# ── Row shape ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class NotificationContentDailyRow:
    """
    Typed row shape for fct_notification_content_daily.

    content_day_id has no PK constraint; treated as the stable de facto key.
    notification_date_key is an INTEGER partition key; str | None.
    read_rate_pct is DECIMAL(5,2); float | None.
    """

    content_day_id: str
    content_id: str | None
    notification_date_key: str | None
    recipient_count: int | None
    read_count: int | None
    read_rate_pct: float | None
    first_sent_at_utc: datetime | None
    last_sent_at_utc: datetime | None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> NotificationContentDailyRow:
        """Normalize a raw warehouse row into a typed NotificationContentDailyRow."""
        return cls(
            content_day_id=normalize_string_id(row["content_day_id"], field_name="content_day_id"),
            content_id=normalize_nullable_string_id(row.get("content_id"), field_name="content_id"),
            notification_date_key=str(row["notification_date_key"]) if row.get("notification_date_key") is not None else None,
            recipient_count=int(row["recipient_count"]) if row.get("recipient_count") is not None else None,
            read_count=int(row["read_count"]) if row.get("read_count") is not None else None,
            read_rate_pct=float(row["read_rate_pct"]) if row.get("read_rate_pct") is not None else None,
            first_sent_at_utc=warehouse_value_to_utc_datetime(row.get("first_sent_at_utc")),
            last_sent_at_utc=warehouse_value_to_utc_datetime(row.get("last_sent_at_utc")),
        )
