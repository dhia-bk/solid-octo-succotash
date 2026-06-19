"""
Warehouse schema for fct_user_behavior.

Source table: fct_user_behavior
Domain: intelligence
Inclusion mode: GRAPH_ENRICHMENT — enriches PersonaState construction
Graph entity: PersonaState (enrichment input; not the canonical node itself)
Freshness field: last_calculated_at

PCM stage and behaviour label per user, computed by the behaviour model.
These signals are inputs to PersonaState node construction in the temporal
pipeline — they are not the PersonaState node themselves.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.core.constants import GRAPH_ENRICHMENT, PERSONA_STATE
from app.core.ids import normalize_nullable_string_id, normalize_string_id
from app.core.time import warehouse_value_to_utc_datetime

# ── Module-level constants ────────────────────────────────────────────────────

SOURCE_NAME: str = "fct_user_behavior"
INCLUSION_MODE: str = GRAPH_ENRICHMENT
PRIMARY_KEYS: tuple[str, ...] = ("id",)
FRESHNESS_FIELD: str | None = "last_calculated_at"
GRAPH_ENTITY_MAPPINGS: tuple[str, ...] = (PERSONA_STATE,)


# ── Row shape ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class UserBehaviorRow:
    """
    Typed row shape for fct_user_behavior.

    birfing_coefficient and frustration_bias are FLOAT in the DWH.
    id is an INTEGER PK; kept as int at this layer.
    """

    id: int
    user_id: str | None
    behaviour_label: str | None
    birfing_coefficient: float | None
    frustration_bias: float | None
    total_sessions: int | None
    total_engagement_signals: int | None
    pcm_stage: str | None
    last_calculated_at: datetime | None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> UserBehaviorRow:
        """Normalize a raw warehouse row into a typed UserBehaviorRow."""
        return cls(
            id=int(normalize_string_id(row["id"], field_name="id")),
            user_id=normalize_nullable_string_id(row.get("user_id"), field_name="user_id"),
            behaviour_label=row.get("behaviour_label"),
            birfing_coefficient=float(row["birfing_coefficient"]) if row.get("birfing_coefficient") is not None else None,
            frustration_bias=float(row["frustration_bias"]) if row.get("frustration_bias") is not None else None,
            total_sessions=int(row["total_sessions"]) if row.get("total_sessions") is not None else None,
            total_engagement_signals=int(row["total_engagement_signals"]) if row.get("total_engagement_signals") is not None else None,
            pcm_stage=row.get("pcm_stage"),
            last_calculated_at=warehouse_value_to_utc_datetime(row.get("last_calculated_at")),
        )
