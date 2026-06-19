"""
Warehouse schema for fct_prediction_duels.

Source table: fct_prediction_duels
Domain: competition
Inclusion mode: GRAPH_CORE — direct graph node creation
Graph entity: Duel
Freshness field: created_at_utc

Head-to-head prediction duels between two users with coin stakes.
Feeds Duel nodes and CHALLENGED relationship (User → Duel).

DWH type notes:
    duel_id    — VARCHAR(100) in DWH; str (spec suggested int).
    fixture_id — VARCHAR(100) in DWH; str | None (spec suggested int).
    is_processed — TINYINT 0/1.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.core.constants import DUEL, GRAPH_CORE
from app.core.ids import normalize_nullable_string_id, normalize_string_id
from app.core.time import warehouse_value_to_utc_datetime

# ── Module-level constants ────────────────────────────────────────────────────

SOURCE_NAME: str = "fct_prediction_duels"
INCLUSION_MODE: str = GRAPH_CORE
PRIMARY_KEYS: tuple[str, ...] = ("duel_id",)
FRESHNESS_FIELD: str | None = "created_at_utc"
GRAPH_ENTITY_MAPPINGS: tuple[str, ...] = (DUEL,)


# ── Row shape ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class PredictionDuelsRow:
    """
    Typed row shape for fct_prediction_duels.

    TINYINT fields (0/1 integers, not booleans in the DWH):
        is_processed

    duel_id and fixture_id are VARCHAR in the DWH; stored as str / str | None.
    """

    duel_id: str
    fixture_id: str | None
    sender_user_id: str | None
    receiver_user_id: str | None
    sender_prediction_id: str | None
    receiver_prediction_id: str | None
    entry_fee: int | None
    status: str | None
    winner_user_id: str | None
    is_processed: int | None
    created_at_utc: datetime | None
    processed_at_utc: datetime | None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> PredictionDuelsRow:
        """Normalize a raw warehouse row into a typed PredictionDuelsRow."""
        return cls(
            duel_id=normalize_string_id(row["duel_id"], field_name="duel_id"),
            fixture_id=normalize_nullable_string_id(row.get("fixture_id"), field_name="fixture_id"),
            sender_user_id=normalize_nullable_string_id(row.get("sender_user_id"), field_name="sender_user_id"),
            receiver_user_id=normalize_nullable_string_id(row.get("receiver_user_id"), field_name="receiver_user_id"),
            sender_prediction_id=normalize_nullable_string_id(row.get("sender_prediction_id"), field_name="sender_prediction_id"),
            receiver_prediction_id=normalize_nullable_string_id(row.get("receiver_prediction_id"), field_name="receiver_prediction_id"),
            entry_fee=int(row["entry_fee"]) if row.get("entry_fee") is not None else None,
            status=row.get("status"),
            winner_user_id=normalize_nullable_string_id(row.get("winner_user_id"), field_name="winner_user_id"),
            is_processed=int(row["is_processed"]) if row.get("is_processed") is not None else None,
            created_at_utc=warehouse_value_to_utc_datetime(row.get("created_at_utc")),
            processed_at_utc=warehouse_value_to_utc_datetime(row.get("processed_at_utc")),
        )
