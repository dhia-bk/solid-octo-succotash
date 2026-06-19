"""
Warehouse schema for dim_leagues.

Source table: dim_leagues
Domain: sports_core
Inclusion mode: GRAPH_CORE — direct graph node creation
Graph entity: League
Freshness field: updated_at

Core league catalog. Feeds IN_LEAGUE (Match → League) and PLAYS_IN
(Team → League) relationships, and serves as a grouping axis for
tribe-level analytics.

Note: season is stored as INTEGER in the DWH (e.g. 2024) but is typed
as str | None here because season values function as labels rather than
quantities. The transformer can format them as "2024" without loss.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.core.constants import GRAPH_CORE, LEAGUE
from app.core.ids import normalize_string_id
from app.core.time import warehouse_value_to_utc_datetime

# ── Module-level constants ────────────────────────────────────────────────────

SOURCE_NAME: str = "dim_leagues"
INCLUSION_MODE: str = GRAPH_CORE
PRIMARY_KEYS: tuple[str, ...] = ("league_id",)
FRESHNESS_FIELD: str | None = "updated_at"
GRAPH_ENTITY_MAPPINGS: tuple[str, ...] = (LEAGUE,)


# ── Row shape ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class LeaguesRow:
    """
    Typed row shape for dim_leagues.

    TINYINT fields (0/1 integers, not booleans in the DWH):
        is_active

    Type overrides vs raw DWH type:
        season — DWH stores INTEGER; exposed as str | None because season
                 values are used as labels (e.g. "2024"), not quantities.
    """

    league_id: int
    league_name: str | None
    country: str | None
    country_code: str | None
    country_flag: str | None
    season: str | None
    league_logo: str | None
    is_active: int | None
    created_at: datetime | None
    updated_at: datetime | None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> LeaguesRow:
        """Normalize a raw warehouse row into a typed LeaguesRow."""
        return cls(
            league_id=int(normalize_string_id(row["league_id"], field_name="league_id")),
            league_name=row.get("league_name"),
            country=row.get("country"),
            country_code=row.get("country_code"),
            country_flag=row.get("country_flag"),
            season=str(row["season"]) if row.get("season") is not None else None,
            league_logo=row.get("league_logo"),
            is_active=int(row["is_active"]) if row.get("is_active") is not None else None,
            created_at=warehouse_value_to_utc_datetime(row.get("created_at")),
            updated_at=warehouse_value_to_utc_datetime(row.get("updated_at")),
        )
