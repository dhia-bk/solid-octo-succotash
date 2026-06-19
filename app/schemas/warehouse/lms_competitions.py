"""
Warehouse schema for dim_lms_competitions.

Source table: dim_lms_competitions
Domain: competition
Inclusion mode: GRAPH_CORE — direct graph node creation
Graph entity: LMSCompetition
Freshness field: created_at

Last Man Standing private league elimination competition dimension.
No declared PK constraint in the DWH; lms_competition_id treated as stable.
Feeds LMSCompetition nodes and PARTICIPATED_IN relationship (User → LMSCompetition).

DWH type note:
    lms_competition_id — VARCHAR(50) in DWH; str (spec suggested int).
    created_by_user_id, winner_user_id — VARCHAR(100); str | None.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.core.constants import GRAPH_CORE, LMS_COMPETITION
from app.core.ids import normalize_nullable_string_id, normalize_string_id
from app.core.time import warehouse_value_to_utc_datetime

# ── Module-level constants ────────────────────────────────────────────────────

SOURCE_NAME: str = "dim_lms_competitions"
INCLUSION_MODE: str = GRAPH_CORE
PRIMARY_KEYS: tuple[str, ...] = ("lms_competition_id",)
FRESHNESS_FIELD: str | None = "created_at"
GRAPH_ENTITY_MAPPINGS: tuple[str, ...] = (LMS_COMPETITION,)


# ── Row shape ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class LmsCompetitionsRow:
    """
    Typed row shape for dim_lms_competitions.

    lms_competition_id is VARCHAR(50) in the DWH; stored as str.
    No declared unique constraint in the DWH — treat lms_competition_id
    as the stable de facto key.
    """

    lms_competition_id: str
    private_league_id: int | None
    competition_name: str | None
    created_by_user_id: str | None
    season_year: int | None
    start_gameweek: int | None
    end_gameweek: int | None
    entry_fee_coins: int | None
    prize_pool_coins: int | None
    max_participants: int | None
    current_participants: int | None
    survivors_remaining: int | None
    elimination_rule: str | None
    status: str | None
    winner_user_id: str | None
    completed_at: datetime | None
    created_at: datetime | None
    current_round: int | None
    winning_date: datetime | None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> LmsCompetitionsRow:
        """Normalize a raw warehouse row into a typed LmsCompetitionsRow."""
        return cls(
            lms_competition_id=normalize_string_id(row["lms_competition_id"], field_name="lms_competition_id"),
            private_league_id=int(row["private_league_id"]) if row.get("private_league_id") is not None else None,
            competition_name=row.get("competition_name"),
            created_by_user_id=normalize_nullable_string_id(row.get("created_by_user_id"), field_name="created_by_user_id"),
            season_year=int(row["season_year"]) if row.get("season_year") is not None else None,
            start_gameweek=int(row["start_gameweek"]) if row.get("start_gameweek") is not None else None,
            end_gameweek=int(row["end_gameweek"]) if row.get("end_gameweek") is not None else None,
            entry_fee_coins=int(row["entry_fee_coins"]) if row.get("entry_fee_coins") is not None else None,
            prize_pool_coins=int(row["prize_pool_coins"]) if row.get("prize_pool_coins") is not None else None,
            max_participants=int(row["max_participants"]) if row.get("max_participants") is not None else None,
            current_participants=int(row["current_participants"]) if row.get("current_participants") is not None else None,
            survivors_remaining=int(row["survivors_remaining"]) if row.get("survivors_remaining") is not None else None,
            elimination_rule=row.get("elimination_rule"),
            status=row.get("status"),
            winner_user_id=normalize_nullable_string_id(row.get("winner_user_id"), field_name="winner_user_id"),
            completed_at=warehouse_value_to_utc_datetime(row.get("completed_at")),
            created_at=warehouse_value_to_utc_datetime(row.get("created_at")),
            current_round=int(row["current_round"]) if row.get("current_round") is not None else None,
            winning_date=warehouse_value_to_utc_datetime(row.get("winning_date")),
        )
