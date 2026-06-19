"""
Warehouse schema for dim_teams.

Source table: dim_teams
Domain: sports_core
Inclusion mode: GRAPH_CORE — direct graph node creation
Graph entity: Team
Freshness field: None (static dimension — full refresh on every run)

Core team catalog. Changes infrequently; no timestamp column in DWH.
Feeds FAVORS, HAS_AFFINITY, HOME_TEAM, and AWAY_TEAM relationships.

Note: team_id is VARCHAR(100) in the DWH despite being conceptually
numeric in some contexts. It is kept as str here to match the source
type exactly. The transformer normalises it via normalize_string_id.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.core.constants import GRAPH_CORE, TEAM
from app.core.ids import normalize_string_id

# ── Module-level constants ────────────────────────────────────────────────────

SOURCE_NAME: str = "dim_teams"
INCLUSION_MODE: str = GRAPH_CORE
PRIMARY_KEYS: tuple[str, ...] = ("team_id",)
FRESHNESS_FIELD: str | None = None
GRAPH_ENTITY_MAPPINGS: tuple[str, ...] = (TEAM,)


# ── Row shape ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class TeamsRow:
    """
    Typed row shape for dim_teams.

    team_id is VARCHAR(100) in the DWH — stored as str, not int.
    """

    team_id: str
    team_name: str | None
    team_code: str | None
    country: str | None
    venue_name: str | None
    team_logo: str | None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> TeamsRow:
        """Normalize a raw warehouse row into a typed TeamsRow."""
        return cls(
            team_id=normalize_string_id(row["team_id"], field_name="team_id"),
            team_name=row.get("team_name"),
            team_code=row.get("team_code"),
            country=row.get("country"),
            venue_name=row.get("venue_name"),
            team_logo=row.get("team_logo"),
        )
