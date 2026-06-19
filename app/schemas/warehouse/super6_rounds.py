"""
Warehouse schema for dim_super6_rounds.

Source table: dim_super6_rounds
Domain: competition
Inclusion mode: GRAPH_CORE — direct graph node creation
Graph entity: Super6Round
Freshness field: start_date_utc

Super6 competition round dimension. Feeds Super6Round nodes, HAS_FIXTURE
relationship (Super6Round → Match), and PARTICIPATED_IN relationship
(User → Super6Round).

DWH type note:
    super6_round_id — VARCHAR(100) in DWH; str (spec suggested int).
    is_active       — TINYINT 0/1.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.core.constants import GRAPH_CORE, SUPER6_ROUND
from app.core.ids import normalize_string_id
from app.core.time import warehouse_value_to_utc_datetime

# ── Module-level constants ────────────────────────────────────────────────────

SOURCE_NAME: str = "dim_super6_rounds"
INCLUSION_MODE: str = GRAPH_CORE
PRIMARY_KEYS: tuple[str, ...] = ("super6_round_id",)
FRESHNESS_FIELD: str | None = "start_date_utc"
GRAPH_ENTITY_MAPPINGS: tuple[str, ...] = (SUPER6_ROUND,)


# ── Row shape ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Super6RoundsRow:
    """
    Typed row shape for dim_super6_rounds.

    TINYINT fields (0/1 integers, not booleans in the DWH):
        is_active

    super6_round_id is VARCHAR(100) in the DWH; stored as str.
    """

    super6_round_id: str
    round_number: int | None
    start_date_utc: datetime | None
    end_date_utc: datetime | None
    is_active: int | None
    created_at_utc: datetime | None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> Super6RoundsRow:
        """Normalize a raw warehouse row into a typed Super6RoundsRow."""
        return cls(
            super6_round_id=normalize_string_id(row["super6_round_id"], field_name="super6_round_id"),
            round_number=int(row["round_number"]) if row.get("round_number") is not None else None,
            start_date_utc=warehouse_value_to_utc_datetime(row.get("start_date_utc")),
            end_date_utc=warehouse_value_to_utc_datetime(row.get("end_date_utc")),
            is_active=int(row["is_active"]) if row.get("is_active") is not None else None,
            created_at_utc=warehouse_value_to_utc_datetime(row.get("created_at_utc")),
        )
