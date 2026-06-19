"""
Warehouse schema for dim_fixtures.

Source table: dim_fixtures
Domain: sports_core
Inclusion mode: GRAPH_CORE — direct graph node creation
Graph entity: Match
Freshness field: kickoff_at_utc

Core fixture (match) catalog. Feeds PREDICTED (User → Match), HOME_TEAM
(Match → Team), AWAY_TEAM (Match → Team), IN_LEAGUE (Match → League),
ABOUT (PredictionDiscussion → Match), and HAS_FIXTURE (Super6Round → Match)
relationships.

DWH type notes:
  fixture_id      — VARCHAR(100) in DWH; kept as str (matches how IDs are
                    referenced across all prediction and discussion tables).
  home_team_id    — VARCHAR(100) in DWH; str (matches dim_teams.team_id type).
  away_team_id    — VARCHAR(100) in DWH; str (matches dim_teams.team_id type).
  kickoff_date_key — INTEGER in DWH (yyyymmdd partition key); exposed as
                    str | None since it is used as a partition label, not a
                    quantity. E.g. 20240315 → "20240315".
  has_discussion  — TINYINT 0/1.
  result_known    — TINYINT 0/1.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.core.constants import GRAPH_CORE, MATCH
from app.core.ids import normalize_nullable_string_id, normalize_string_id
from app.core.time import warehouse_value_to_utc_datetime

# ── Module-level constants ────────────────────────────────────────────────────

SOURCE_NAME: str = "dim_fixtures"
INCLUSION_MODE: str = GRAPH_CORE
PRIMARY_KEYS: tuple[str, ...] = ("fixture_id",)
FRESHNESS_FIELD: str | None = "kickoff_at_utc"
GRAPH_ENTITY_MAPPINGS: tuple[str, ...] = (MATCH,)


# ── Row shape ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class FixturesRow:
    """
    Typed row shape for dim_fixtures.

    TINYINT fields (0/1 integers, not booleans in the DWH):
        has_discussion
        result_known

    fixture_id, home_team_id, and away_team_id are VARCHAR in the DWH and
    are stored as str here. kickoff_date_key is INTEGER in the DWH but
    exposed as str | None (partition label, not a quantity).
    """

    fixture_id: str
    away_team_logo: str | None
    away_team_name: str | None
    country: str | None
    country_flag: str | None
    elapsed_time: int | None
    extra_time_score: str | None
    final_game_score: str | None
    home_team_logo: str | None
    home_team_name: str | None
    kickoff_at_utc: datetime | None
    league_id: int | None
    league_logo: str | None
    league_name: str | None
    penalty_score: str | None
    season: str | None
    status: str | None
    kickoff_date_key: str | None
    home_team_id: str | None
    away_team_id: str | None
    public_prediction_count: int | None
    private_prediction_count: int | None
    has_discussion: int | None
    result_known: int | None
    fixture_era: str | None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> FixturesRow:
        """Normalize a raw warehouse row into a typed FixturesRow."""
        return cls(
            fixture_id=normalize_string_id(row["fixture_id"], field_name="fixture_id"),
            away_team_logo=row.get("away_team_logo"),
            away_team_name=row.get("away_team_name"),
            country=row.get("country"),
            country_flag=row.get("country_flag"),
            elapsed_time=int(row["elapsed_time"]) if row.get("elapsed_time") is not None else None,
            extra_time_score=row.get("extra_time_score"),
            final_game_score=row.get("final_game_score"),
            home_team_logo=row.get("home_team_logo"),
            home_team_name=row.get("home_team_name"),
            kickoff_at_utc=warehouse_value_to_utc_datetime(row.get("kickoff_at_utc")),
            league_id=int(row["league_id"]) if row.get("league_id") is not None else None,
            league_logo=row.get("league_logo"),
            league_name=row.get("league_name"),
            penalty_score=row.get("penalty_score"),
            season=row.get("season"),
            status=row.get("status"),
            kickoff_date_key=str(row["kickoff_date_key"]) if row.get("kickoff_date_key") is not None else None,
            home_team_id=normalize_nullable_string_id(row.get("home_team_id"), field_name="home_team_id"),
            away_team_id=normalize_nullable_string_id(row.get("away_team_id"), field_name="away_team_id"),
            public_prediction_count=int(row["public_prediction_count"]) if row.get("public_prediction_count") is not None else None,
            private_prediction_count=int(row["private_prediction_count"]) if row.get("private_prediction_count") is not None else None,
            has_discussion=int(row["has_discussion"]) if row.get("has_discussion") is not None else None,
            result_known=int(row["result_known"]) if row.get("result_known") is not None else None,
            fixture_era=row.get("fixture_era"),
        )
