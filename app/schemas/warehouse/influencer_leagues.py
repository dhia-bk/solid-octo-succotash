"""
Warehouse schema for dim_influencer_leagues.

Source table: dim_influencer_leagues
Domain: ops
Inclusion mode: GRAPH_CORE — direct graph node creation
Graph entity: InfluencerLeague
Freshness field: updated_at

Influencer league dimension. Feeds InfluencerLeague nodes and PROMOTES
relationship (InfluencerLeague → PrivateLeague).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.core.constants import GRAPH_CORE, INFLUENCER_LEAGUE
from app.core.ids import normalize_string_id
from app.core.time import warehouse_value_to_utc_datetime

# ── Module-level constants ────────────────────────────────────────────────────

SOURCE_NAME: str = "dim_influencer_leagues"
INCLUSION_MODE: str = GRAPH_CORE
PRIMARY_KEYS: tuple[str, ...] = ("influencer_league_id",)
FRESHNESS_FIELD: str | None = "updated_at"
GRAPH_ENTITY_MAPPINGS: tuple[str, ...] = (INFLUENCER_LEAGUE,)


# ── Row shape ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class InfluencerLeaguesRow:
    """
    Typed row shape for dim_influencer_leagues.

    influencer_league_id is INTEGER PK; stored as int.
    created_at and updated_at are TIMESTAMP in the DWH.
    """

    influencer_league_id: int
    name: str | None
    description: str | None
    created_at: datetime | None
    updated_at: datetime | None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> InfluencerLeaguesRow:
        """Normalize a raw warehouse row into a typed InfluencerLeaguesRow."""
        return cls(
            influencer_league_id=int(normalize_string_id(row["influencer_league_id"], field_name="influencer_league_id")),
            name=row.get("name"),
            description=row.get("description"),
            created_at=warehouse_value_to_utc_datetime(row.get("created_at")),
            updated_at=warehouse_value_to_utc_datetime(row.get("updated_at")),
        )
