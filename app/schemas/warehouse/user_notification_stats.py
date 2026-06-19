"""
Warehouse schema for fct_user_notification_stats.

Source table: fct_user_notification_stats
Domain: engagement
Inclusion mode: FEATURE_SOURCE — feeds notification feature view only
Graph entity: none
Freshness field: last_notification_at_utc

Per-user notification engagement aggregates. No declared PK constraint;
user_id treated as the stable de facto key. Feeds the notification feature
view in the serving layer.

DWH type notes:
    read_rate_pct, consistency_score — DECIMAL(5,2); float | None.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.core.constants import FEATURE_SOURCE
from app.core.ids import normalize_string_id
from app.core.time import warehouse_value_to_utc_datetime

# ── Module-level constants ────────────────────────────────────────────────────

SOURCE_NAME: str = "fct_user_notification_stats"
INCLUSION_MODE: str = FEATURE_SOURCE
PRIMARY_KEYS: tuple[str, ...] = ("user_id",)
FRESHNESS_FIELD: str | None = "last_notification_at_utc"
GRAPH_ENTITY_MAPPINGS: tuple[str, ...] = ()


# ── Row shape ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class UserNotificationStatsRow:
    """
    Typed row shape for fct_user_notification_stats.

    user_id has no PK constraint; treated as the stable de facto key.
    read_rate_pct and consistency_score are DECIMAL(5,2); float | None.
    """

    user_id: str
    total_received: int | None
    total_read: int | None
    read_rate_pct: float | None
    active_days_received: int | None
    active_days_read: int | None
    consistency_score: float | None
    last_notification_at_utc: datetime | None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> UserNotificationStatsRow:
        """Normalize a raw warehouse row into a typed UserNotificationStatsRow."""
        return cls(
            user_id=normalize_string_id(row["user_id"], field_name="user_id"),
            total_received=int(row["total_received"]) if row.get("total_received") is not None else None,
            total_read=int(row["total_read"]) if row.get("total_read") is not None else None,
            read_rate_pct=float(row["read_rate_pct"]) if row.get("read_rate_pct") is not None else None,
            active_days_received=int(row["active_days_received"]) if row.get("active_days_received") is not None else None,
            active_days_read=int(row["active_days_read"]) if row.get("active_days_read") is not None else None,
            consistency_score=float(row["consistency_score"]) if row.get("consistency_score") is not None else None,
            last_notification_at_utc=warehouse_value_to_utc_datetime(row.get("last_notification_at_utc")),
        )
