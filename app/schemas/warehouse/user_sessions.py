"""
Warehouse schema for fct_user_sessions.

Source table: fct_user_sessions
Domain: intelligence
Inclusion mode: FEATURE_SOURCE — feeds ML feature computation only
Graph entity: none
Freshness field: session_start_utc

Session aggregates per user visit. Too transient and user-anchored for
graph node representation. Consumed by the behaviour model feature pipeline.

DWH type note:
    session_date_key — INTEGER in DWH (yyyymmdd partition key); exposed
                       as str | None — partition label, not a quantity.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.core.constants import FEATURE_SOURCE
from app.core.ids import normalize_nullable_string_id, normalize_string_id
from app.core.time import warehouse_value_to_utc_datetime

# ── Module-level constants ────────────────────────────────────────────────────

SOURCE_NAME: str = "fct_user_sessions"
INCLUSION_MODE: str = FEATURE_SOURCE
PRIMARY_KEYS: tuple[str, ...] = ("session_id",)
FRESHNESS_FIELD: str | None = "session_start_utc"
GRAPH_ENTITY_MAPPINGS: tuple[str, ...] = ()


# ── Row shape ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class UserSessionsRow:
    """
    Typed row shape for fct_user_sessions.

    session_date_key is INTEGER in the DWH but exposed as str | None
    (partition label).
    """

    session_id: str
    user_id: str | None
    session_start_utc: datetime | None
    session_end_utc: datetime | None
    session_duration_seconds: int | None
    session_date_key: str | None
    session_status: str | None
    page_views: int | None
    distinct_page_views: int | None
    landing_page: str | None
    exit_page: str | None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> UserSessionsRow:
        """Normalize a raw warehouse row into a typed UserSessionsRow."""
        return cls(
            session_id=normalize_string_id(row["session_id"], field_name="session_id"),
            user_id=normalize_nullable_string_id(row.get("user_id"), field_name="user_id"),
            session_start_utc=warehouse_value_to_utc_datetime(row.get("session_start_utc")),
            session_end_utc=warehouse_value_to_utc_datetime(row.get("session_end_utc")),
            session_duration_seconds=int(row["session_duration_seconds"]) if row.get("session_duration_seconds") is not None else None,
            session_date_key=str(row["session_date_key"]) if row.get("session_date_key") is not None else None,
            session_status=row.get("session_status"),
            page_views=int(row["page_views"]) if row.get("page_views") is not None else None,
            distinct_page_views=int(row["distinct_page_views"]) if row.get("distinct_page_views") is not None else None,
            landing_page=row.get("landing_page"),
            exit_page=row.get("exit_page"),
        )
