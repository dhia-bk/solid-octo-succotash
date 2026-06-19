"""
Warehouse schema for dim_private_league_members.

Source table: dim_private_league_members
Domain: social
Inclusion mode: GRAPH_CORE — feeds relationship creation
Graph entity: MEMBER_OF relationship (User → PrivateLeague)
Freshness field: joined_at

Membership junction table. The primary source for MEMBER_OF edges.
membership_id may be null in some rows; the transformer must fall back to
the composite key (private_league_id, user_id) for deduplication.

DWH type notes:
    membership_id       — VARCHAR(50) in DWH; nullable, str | None.
    invited_by_user_id  — INTEGER in DWH despite being a user reference;
                          normalized to str | None here for consistency with
                          all other user ID references across the graph.
    is_active, can_post, can_moderate, can_invite — TINYINT 0/1 flags.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.core.constants import GRAPH_CORE, MEMBER_OF
from app.core.ids import normalize_nullable_string_id, normalize_string_id
from app.core.time import warehouse_value_to_utc_datetime

# ── Module-level constants ────────────────────────────────────────────────────

SOURCE_NAME: str = "dim_private_league_members"
INCLUSION_MODE: str = GRAPH_CORE
PRIMARY_KEYS: tuple[str, ...] = ("membership_id",)
FRESHNESS_FIELD: str | None = "joined_at"
GRAPH_ENTITY_MAPPINGS: tuple[str, ...] = (MEMBER_OF,)


# ── Row shape ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class PrivateLeagueMembersRow:
    """
    Typed row shape for dim_private_league_members.

    TINYINT fields (0/1 integers, not booleans in the DWH):
        is_active
        can_post
        can_moderate
        can_invite

    membership_id is nullable in the DWH. When null, use the composite key
    (private_league_id, user_id) for stable row identification.

    invited_by_user_id is stored as INTEGER in the DWH but is a user
    reference; normalized to str | None for cross-entity consistency.
    """

    membership_id: str | None
    private_league_id: int | None
    user_id: str | None
    role: str | None
    joined_at: datetime | None
    invite_code_used: str | None
    invited_by_user_id: str | None
    is_active: int | None
    left_at: datetime | None
    leave_reason: str | None
    can_post: int | None
    can_moderate: int | None
    can_invite: int | None
    division: str | None
    last_active_at_utc: datetime | None
    fixture_participation_count: int | None
    days_since_joined: int | None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> PrivateLeagueMembersRow:
        """Normalize a raw warehouse row into a typed PrivateLeagueMembersRow."""
        return cls(
            membership_id=normalize_nullable_string_id(row.get("membership_id"), field_name="membership_id"),
            private_league_id=int(row["private_league_id"]) if row.get("private_league_id") is not None else None,
            user_id=normalize_nullable_string_id(row.get("user_id"), field_name="user_id"),
            role=row.get("role"),
            joined_at=warehouse_value_to_utc_datetime(row.get("joined_at")),
            invite_code_used=row.get("invite_code_used"),
            invited_by_user_id=normalize_nullable_string_id(
                str(row["invited_by_user_id"]) if row.get("invited_by_user_id") is not None else None,
                field_name="invited_by_user_id",
            ),
            is_active=int(row["is_active"]) if row.get("is_active") is not None else None,
            left_at=warehouse_value_to_utc_datetime(row.get("left_at")),
            leave_reason=row.get("leave_reason"),
            can_post=int(row["can_post"]) if row.get("can_post") is not None else None,
            can_moderate=int(row["can_moderate"]) if row.get("can_moderate") is not None else None,
            can_invite=int(row["can_invite"]) if row.get("can_invite") is not None else None,
            division=row.get("division"),
            last_active_at_utc=warehouse_value_to_utc_datetime(row.get("last_active_at_utc")),
            fixture_participation_count=int(row["fixture_participation_count"]) if row.get("fixture_participation_count") is not None else None,
            days_since_joined=int(row["days_since_joined"]) if row.get("days_since_joined") is not None else None,
        )
