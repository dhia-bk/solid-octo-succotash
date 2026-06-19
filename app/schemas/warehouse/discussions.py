"""
Warehouse schema for dim_discussions.

Source table: dim_discussions
Domain: social
Inclusion mode: GRAPH_CORE — direct graph node creation
Graph entity: Discussion
Freshness field: created_at_utc

Fixture-linked discussion threads. Feeds JOINED_DISCUSSION (User → Discussion)
relationship and links discussions to their parent Match via fixture_id.

DWH type notes:
    discussion_id — INTEGER PK; stored as int.
    fixture_id    — VARCHAR(255) in DWH despite the spec suggesting int;
                    stored as str | None to match the actual column type and
                    remain consistent with dim_fixtures.fixture_id (VARCHAR).
    is_closed     — TINYINT 0/1 flag.
    created_at_utc — TIMESTAMP in DWH.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.core.constants import DISCUSSION, GRAPH_CORE
from app.core.ids import normalize_nullable_string_id, normalize_string_id
from app.core.time import warehouse_value_to_utc_datetime

# ── Module-level constants ────────────────────────────────────────────────────

SOURCE_NAME: str = "dim_discussions"
INCLUSION_MODE: str = GRAPH_CORE
PRIMARY_KEYS: tuple[str, ...] = ("discussion_id",)
FRESHNESS_FIELD: str | None = "created_at_utc"
GRAPH_ENTITY_MAPPINGS: tuple[str, ...] = (DISCUSSION,)


# ── Row shape ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class DiscussionsRow:
    """
    Typed row shape for dim_discussions.

    TINYINT fields (0/1 integers, not booleans in the DWH):
        is_closed

    fixture_id is VARCHAR(255) in the DWH; stored as str | None to match
    dim_fixtures.fixture_id type.
    """

    discussion_id: int
    fixture_id: str | None
    created_at_utc: datetime | None
    is_closed: int | None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> DiscussionsRow:
        """Normalize a raw warehouse row into a typed DiscussionsRow."""
        return cls(
            discussion_id=int(normalize_string_id(row["discussion_id"], field_name="discussion_id")),
            fixture_id=normalize_nullable_string_id(row.get("fixture_id"), field_name="fixture_id"),
            created_at_utc=warehouse_value_to_utc_datetime(row.get("created_at_utc")),
            is_closed=int(row["is_closed"]) if row.get("is_closed") is not None else None,
        )
