"""
Warehouse schema for fct_moderation_events.

Source table: fct_moderation_events
Domain: ops
Inclusion mode: GRAPH_CORE — direct graph node creation
Graph entity: ModerationEvent
Freshness field: event_at_utc

Moderation action event log. Feeds ModerationEvent nodes and MODERATED
relationship (User → ModerationEvent) for moderator-side actions.

DWH type notes:
    event_id             — VARCHAR(255) in DWH; str (spec suggested int).
    event_date_key       — INTEGER partition key; str | None.
    decision_confidence_score — DECIMAL(5,2); float | None.
    automated_flag       — TINYINT 0/1.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.core.constants import GRAPH_CORE, MODERATION_EVENT
from app.core.ids import normalize_nullable_string_id, normalize_string_id
from app.core.time import warehouse_value_to_utc_datetime

# ── Module-level constants ────────────────────────────────────────────────────

SOURCE_NAME: str = "fct_moderation_events"
INCLUSION_MODE: str = GRAPH_CORE
PRIMARY_KEYS: tuple[str, ...] = ("event_id",)
FRESHNESS_FIELD: str | None = "event_at_utc"
GRAPH_ENTITY_MAPPINGS: tuple[str, ...] = (MODERATION_EVENT,)


# ── Row shape ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ModerationEventsRow:
    """
    Typed row shape for fct_moderation_events.

    TINYINT fields (0/1 integers, not booleans in the DWH):
        automated_flag

    event_id is VARCHAR(255) in the DWH; stored as str.
    event_date_key is an INTEGER partition key; str | None.
    decision_confidence_score is DECIMAL(5,2); float | None.
    """

    event_id: str
    moderator_user_id: str | None
    target_user_id: str | None
    moderation_type: str | None
    event_at_utc: datetime | None
    event_date_key: str | None
    reason: str | None
    description: str | None
    status: str | None
    content_id: str | None
    content_type: str | None
    moderator_decision: str | None
    appeal_status: str | None
    decision_confidence_score: float | None
    automated_flag: int | None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> ModerationEventsRow:
        """Normalize a raw warehouse row into a typed ModerationEventsRow."""
        return cls(
            event_id=normalize_string_id(row["event_id"], field_name="event_id"),
            moderator_user_id=normalize_nullable_string_id(row.get("moderator_user_id"), field_name="moderator_user_id"),
            target_user_id=normalize_nullable_string_id(row.get("target_user_id"), field_name="target_user_id"),
            moderation_type=row.get("moderation_type"),
            event_at_utc=warehouse_value_to_utc_datetime(row.get("event_at_utc")),
            event_date_key=str(row["event_date_key"]) if row.get("event_date_key") is not None else None,
            reason=row.get("reason"),
            description=row.get("description"),
            status=row.get("status"),
            content_id=normalize_nullable_string_id(row.get("content_id"), field_name="content_id"),
            content_type=row.get("content_type"),
            moderator_decision=row.get("moderator_decision"),
            appeal_status=row.get("appeal_status"),
            decision_confidence_score=float(row["decision_confidence_score"]) if row.get("decision_confidence_score") is not None else None,
            automated_flag=int(row["automated_flag"]) if row.get("automated_flag") is not None else None,
        )
