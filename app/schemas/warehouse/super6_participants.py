"""
Warehouse schema for fct_super6_participants.

Source table: fct_super6_participants
Domain: competition
Inclusion mode: GRAPH_CORE — feeds relationship creation
Graph entity: PARTICIPATED_IN relationship (User → Super6Round)
Freshness field: joined_at_utc

Per-user Super6 round participation facts. Feeds PARTICIPATED_IN edge
properties: total points, correct scores, winner flag.

DWH type notes:
    super6_participant_id — VARCHAR(100) in DWH; str (spec suggested int).
    super6_round_id       — VARCHAR(100) in DWH; str | None (spec suggested int).
    is_winner, is_fully_processed — TINYINT 0/1.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.core.constants import GRAPH_CORE, PARTICIPATED_IN
from app.core.ids import normalize_nullable_string_id, normalize_string_id
from app.core.time import warehouse_value_to_utc_datetime

# ── Module-level constants ────────────────────────────────────────────────────

SOURCE_NAME: str = "fct_super6_participants"
INCLUSION_MODE: str = GRAPH_CORE
PRIMARY_KEYS: tuple[str, ...] = ("super6_participant_id",)
FRESHNESS_FIELD: str | None = "joined_at_utc"
GRAPH_ENTITY_MAPPINGS: tuple[str, ...] = (PARTICIPATED_IN,)


# ── Row shape ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Super6ParticipantsRow:
    """
    Typed row shape for fct_super6_participants.

    TINYINT fields (0/1 integers, not booleans in the DWH):
        is_winner
        is_fully_processed

    super6_participant_id and super6_round_id are VARCHAR in the DWH;
    stored as str / str | None.
    """

    super6_participant_id: str
    user_id: str | None
    super6_round_id: str | None
    joined_at_utc: datetime | None
    total_points: int | None
    correct_scores: int | None
    correct_results: int | None
    wrong_predictions: int | None
    processed_matches: int | None
    is_winner: int | None
    is_fully_processed: int | None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> Super6ParticipantsRow:
        """Normalize a raw warehouse row into a typed Super6ParticipantsRow."""
        return cls(
            super6_participant_id=normalize_string_id(row["super6_participant_id"], field_name="super6_participant_id"),
            user_id=normalize_nullable_string_id(row.get("user_id"), field_name="user_id"),
            super6_round_id=normalize_nullable_string_id(row.get("super6_round_id"), field_name="super6_round_id"),
            joined_at_utc=warehouse_value_to_utc_datetime(row.get("joined_at_utc")),
            total_points=int(row["total_points"]) if row.get("total_points") is not None else None,
            correct_scores=int(row["correct_scores"]) if row.get("correct_scores") is not None else None,
            correct_results=int(row["correct_results"]) if row.get("correct_results") is not None else None,
            wrong_predictions=int(row["wrong_predictions"]) if row.get("wrong_predictions") is not None else None,
            processed_matches=int(row["processed_matches"]) if row.get("processed_matches") is not None else None,
            is_winner=int(row["is_winner"]) if row.get("is_winner") is not None else None,
            is_fully_processed=int(row["is_fully_processed"]) if row.get("is_fully_processed") is not None else None,
        )
