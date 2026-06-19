"""
Warehouse schema for dim_teams_enhanced.

Source table: dim_teams_enhanced
Domain: sports_core
Inclusion mode: GRAPH_ENRICHMENT — enriches existing Team nodes
Graph entity: Team (enrichment; does not create a new node type)
Freshness field: last_fan_joined_at

Adds computed fan analytics to existing Team nodes: fan counts, engagement
scores, growth rates, and demographic signals. team_id is an INTEGER in this
table (unlike dim_teams where it is VARCHAR). The transformer is responsible
for resolving the league_id FK to dim_leagues before writing to the graph.

Note: first_fan_joined_at and last_fan_joined_at are stored as VARCHAR(255)
in the DWH despite representing datetimes. warehouse_value_to_utc_datetime
handles both ISO string and datetime inputs safely.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.core.constants import GRAPH_ENRICHMENT, TEAM
from app.core.ids import normalize_string_id
from app.core.time import warehouse_value_to_utc_datetime

# ── Module-level constants ────────────────────────────────────────────────────

SOURCE_NAME: str = "dim_teams_enhanced"
INCLUSION_MODE: str = GRAPH_ENRICHMENT
PRIMARY_KEYS: tuple[str, ...] = ("team_id",)
FRESHNESS_FIELD: str | None = "last_fan_joined_at"
GRAPH_ENTITY_MAPPINGS: tuple[str, ...] = (TEAM,)


# ── Row shape ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class TeamsEnhancedRow:
    """
    Typed row shape for dim_teams_enhanced.

    team_id is INTEGER in this table (differs from dim_teams where it is
    VARCHAR). Stored as int here; the transformer normalises to string for
    graph merge.

    league_id is a FK to dim_leagues. The transformer must resolve this
    before writing Team node properties.

    first_fan_joined_at and last_fan_joined_at are VARCHAR(255) in the DWH
    but semantically are datetimes; normalized via warehouse_value_to_utc_datetime.
    """

    team_id: int
    team_name: str | None
    team_logo: str | None
    league_id: int | None
    country: str | None
    total_fans: int | None
    fan_percentage: float | None
    fan_rank: int | None
    top_fan_country: str | None
    top_fan_gender: str | None
    avg_fan_age: float | None
    total_predictions_for_team: int | None
    total_predictions_by_fans: int | None
    fan_engagement_score: float | None
    active_fans_last_30d: int | None
    fan_retention_rate: float | None
    first_fan_joined_at: datetime | None
    last_fan_joined_at: datetime | None
    new_fans_last_30d: int | None
    fan_growth_rate: float | None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> TeamsEnhancedRow:
        """Normalize a raw warehouse row into a typed TeamsEnhancedRow."""
        return cls(
            team_id=int(normalize_string_id(row["team_id"], field_name="team_id")),
            team_name=row.get("team_name"),
            team_logo=row.get("team_logo"),
            league_id=int(row["league_id"]) if row.get("league_id") is not None else None,
            country=row.get("country"),
            total_fans=int(row["total_fans"]) if row.get("total_fans") is not None else None,
            fan_percentage=float(row["fan_percentage"]) if row.get("fan_percentage") is not None else None,
            fan_rank=int(row["fan_rank"]) if row.get("fan_rank") is not None else None,
            top_fan_country=row.get("top_fan_country"),
            top_fan_gender=row.get("top_fan_gender"),
            avg_fan_age=float(row["avg_fan_age"]) if row.get("avg_fan_age") is not None else None,
            total_predictions_for_team=int(row["total_predictions_for_team"]) if row.get("total_predictions_for_team") is not None else None,
            total_predictions_by_fans=int(row["total_predictions_by_fans"]) if row.get("total_predictions_by_fans") is not None else None,
            fan_engagement_score=float(row["fan_engagement_score"]) if row.get("fan_engagement_score") is not None else None,
            active_fans_last_30d=int(row["active_fans_last_30d"]) if row.get("active_fans_last_30d") is not None else None,
            fan_retention_rate=float(row["fan_retention_rate"]) if row.get("fan_retention_rate") is not None else None,
            first_fan_joined_at=warehouse_value_to_utc_datetime(row.get("first_fan_joined_at")),
            last_fan_joined_at=warehouse_value_to_utc_datetime(row.get("last_fan_joined_at")),
            new_fans_last_30d=int(row["new_fans_last_30d"]) if row.get("new_fans_last_30d") is not None else None,
            fan_growth_rate=float(row["fan_growth_rate"]) if row.get("fan_growth_rate") is not None else None,
        )
