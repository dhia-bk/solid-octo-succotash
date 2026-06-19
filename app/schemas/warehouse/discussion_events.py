"""
Warehouse schema for fct_discussion_events.

Source table: fct_discussion_events
Domain: social
Inclusion mode: GRAPH_CORE — feeds relationship creation
Graph entity: JOINED_DISCUSSION relationship (User → Discussion)
Freshness field: event_at_utc

User participation events within fixture and prediction discussions. The
primary source for JOINED_DISCUSSION edge properties (event_type, timestamp).

DWH type notes:
    event_id       — VARCHAR(255) in DWH; stored as str (not int as spec
                     initially suggested).
    user_id        — VARCHAR(255) in DWH; str | None.
    event_date_key — INTEGER in DWH (yyyymmdd partition key); exposed as
                     str | None since it is used as a partition label.
    event_at_utc   — TIMESTAMP in DWH.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.core.constants import GRAPH_CORE, JOINED_DISCUSSION
from app.core.ids import normalize_nullable_string_id, normalize_string_id
from app.core.time import warehouse_value_to_utc_datetime

# ── Module-level constants ────────────────────────────────────────────────────

SOURCE_NAME: str = "fct_discussion_events"
INCLUSION_MODE: str = GRAPH_CORE
PRIMARY_KEYS: tuple[str, ...] = ("event_id",)
FRESHNESS_FIELD: str | None = "event_at_utc"
GRAPH_ENTITY_MAPPINGS: tuple[str, ...] = (JOINED_DISCUSSION,)


# ── Row shape ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class DiscussionEventsRow:
    """
    Typed row shape for fct_discussion_events.

    event_id and user_id are VARCHAR in the DWH; stored as str / str | None.
    event_date_key is INTEGER in the DWH but exposed as str | None
    (partition label, not a numeric quantity).
    """

    event_id: str
    user_id: str | None
    discussion_id: int | None
    prediction_discussion_id: int | None
    event_type: str | None
    event_at_utc: datetime | None
    event_date_key: str | None
    content_preview: str | None
    like_count: int | None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> DiscussionEventsRow:
        """Normalize a raw warehouse row into a typed DiscussionEventsRow."""
        return cls(
            event_id=normalize_string_id(row["event_id"], field_name="event_id"),
            user_id=normalize_nullable_string_id(row.get("user_id"), field_name="user_id"),
            discussion_id=int(row["discussion_id"]) if row.get("discussion_id") is not None else None,
            prediction_discussion_id=int(row["prediction_discussion_id"]) if row.get("prediction_discussion_id") is not None else None,
            event_type=row.get("event_type"),
            event_at_utc=warehouse_value_to_utc_datetime(row.get("event_at_utc")),
            event_date_key=str(row["event_date_key"]) if row.get("event_date_key") is not None else None,
            content_preview=row.get("content_preview"),
            like_count=int(row["like_count"]) if row.get("like_count") is not None else None,
        )
