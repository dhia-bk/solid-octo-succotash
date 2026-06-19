"""
Warehouse schema for app_users.

Source table: app_users
Domain: identity
Inclusion mode: GRAPH_ENRICHMENT — enriches User nodes with auth metadata
Graph entity: User (enrichment; does not create a new node type)
Freshness field: updated_at

Auth bridge table. Enriches existing User nodes with login provider and
credential metadata. Links to dim_users via email or username join.

PII WARNING:
    email    — PII field. Must NOT be written to graph properties or logs.
               Used only for the join to dim_users; drop before graph load.
    password — PII/credential field. Must NEVER be written to graph properties,
               logs, or any downstream system. The transformer must assert
               this field is dropped before any processing step.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.core.constants import GRAPH_ENRICHMENT, USER
from app.core.ids import normalize_string_id
from app.core.time import warehouse_value_to_utc_datetime

# ── Module-level constants ────────────────────────────────────────────────────

SOURCE_NAME: str = "app_users"
INCLUSION_MODE: str = GRAPH_ENRICHMENT
PRIMARY_KEYS: tuple[str, ...] = ("id",)
FRESHNESS_FIELD: str | None = "updated_at"
GRAPH_ENTITY_MAPPINGS: tuple[str, ...] = (USER,)


# ── Row shape ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class AppUsersRow:
    """
    Typed row shape for app_users.

    TINYINT fields (0/1 integers, not booleans in the DWH):
        is_seeded

    PII fields — must NOT be written to the graph or logs:
        email     (used for join to dim_users only; drop before graph load)
        password  (credential; must be asserted absent before any processing)
    """

    id: str
    email: str | None
    username: str | None
    is_seeded: int | None
    password: str | None
    created_at: datetime | None
    updated_at: datetime | None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> AppUsersRow:
        """Normalize a raw warehouse row into a typed AppUsersRow."""
        return cls(
            id=normalize_string_id(row["id"], field_name="id"),
            email=row.get("email"),           # PII — join key only; drop before graph load
            username=row.get("username"),
            is_seeded=int(row["is_seeded"]) if row.get("is_seeded") is not None else None,
            password=row.get("password"),      # CREDENTIAL — must be dropped before any processing
            created_at=warehouse_value_to_utc_datetime(row.get("created_at")),
            updated_at=warehouse_value_to_utc_datetime(row.get("updated_at")),
        )
