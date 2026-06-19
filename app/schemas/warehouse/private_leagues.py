"""
Warehouse schema for dim_private_leagues.

Source table: dim_private_leagues
Domain: social
Inclusion mode: GRAPH_CORE — direct graph node creation
Graph entity: PrivateLeague
Freshness field: None (no timestamp column in DWH — use full refresh or
                 numeric watermark on private_league_id)

Private leagues are the primary social grouping mechanism on the platform.
Feeds MEMBER_OF relationship (User → PrivateLeague) and serves as the
owner entity for league-level tribe detection.

DWH type note:
    is_generic — stored as INTEGER in the DWH (not TINYINT), but is
                 semantically 0/1 and treated as a flag.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.core.constants import GRAPH_CORE, PRIVATE_LEAGUE
from app.core.ids import normalize_nullable_string_id, normalize_string_id

# ── Module-level constants ────────────────────────────────────────────────────

SOURCE_NAME: str = "dim_private_leagues"
INCLUSION_MODE: str = GRAPH_CORE
PRIMARY_KEYS: tuple[str, ...] = ("private_league_id",)
FRESHNESS_FIELD: str | None = None
GRAPH_ENTITY_MAPPINGS: tuple[str, ...] = (PRIVATE_LEAGUE,)


# ── Row shape ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class PrivateLeaguesRow:
    """
    Typed row shape for dim_private_leagues.

    is_generic is an INTEGER 0/1 flag in the DWH (not a TINYINT column,
    but semantically equivalent). Stored as int | None.
    """

    private_league_id: int
    owner_user_id: str | None
    league_name: str | None
    image: str | None
    about: str | None
    member_count: int | None
    join_code: str | None
    is_generic: int | None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> PrivateLeaguesRow:
        """Normalize a raw warehouse row into a typed PrivateLeaguesRow."""
        return cls(
            private_league_id=int(normalize_string_id(row["private_league_id"], field_name="private_league_id")),
            owner_user_id=normalize_nullable_string_id(row.get("owner_user_id"), field_name="owner_user_id"),
            league_name=row.get("league_name"),
            image=row.get("image"),
            about=row.get("about"),
            member_count=int(row["member_count"]) if row.get("member_count") is not None else None,
            join_code=row.get("join_code"),
            is_generic=int(row["is_generic"]) if row.get("is_generic") is not None else None,
        )
