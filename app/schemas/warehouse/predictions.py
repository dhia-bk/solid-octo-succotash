"""
Warehouse schema for fct_predictions.

Source table: fct_predictions
Domain: competition
Inclusion mode: GRAPH_CORE — feeds relationship creation
Graph entity: PREDICTED relationship (User → Match)
Freshness field: predicted_at_utc

Unified prediction fact table covering public and private league predictions.
Primary source for PREDICTED edge properties: outcome, accuracy, points,
prediction context, and era.

DWH type notes:
    fixture_id          — VARCHAR(100); str | None (spec suggested int).
    influencer_league_id — VARCHAR(100); str | None (spec suggested int).
    private_league_id   — VARCHAR(100); str | None (spec suggested int).
    points_awarded      — DECIMAL(10,2); float | None (spec suggested int).
    prediction_date_key,
    kickoff_date_key,
    result_date_key     — INTEGER partition keys; exposed as str | None
                          (partition labels, not quantities).
    is_correct_result, is_correct_score, is_processed — TINYINT 0/1.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.core.constants import GRAPH_CORE, PREDICTED
from app.core.ids import normalize_nullable_string_id, normalize_string_id
from app.core.time import warehouse_value_to_utc_datetime

# ── Module-level constants ────────────────────────────────────────────────────

SOURCE_NAME: str = "fct_predictions"
INCLUSION_MODE: str = GRAPH_CORE
PRIMARY_KEYS: tuple[str, ...] = ("unified_prediction_id",)
FRESHNESS_FIELD: str | None = "predicted_at_utc"
GRAPH_ENTITY_MAPPINGS: tuple[str, ...] = (PREDICTED,)


# ── Row shape ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class PredictionsRow:
    """
    Typed row shape for fct_predictions.

    TINYINT fields (0/1 integers, not booleans in the DWH):
        is_correct_result
        is_correct_score
        is_processed

    fixture_id, influencer_league_id, and private_league_id are VARCHAR in
    the DWH; stored as str | None. points_awarded is DECIMAL; float | None.
    All *_date_key fields are INTEGER partition keys; str | None.
    """

    unified_prediction_id: str
    prediction_id: str | None
    actual_score: str | None
    fixture_id: str | None
    influencer_league_id: str | None
    is_correct_result: int | None
    is_correct_score: int | None
    is_processed: int | None
    kickoff_at_utc: datetime | None
    league_id: int | None
    points_awarded: float | None
    predicted_at_utc: datetime | None
    predicted_outcome: str | None
    predicted_score: str | None
    prediction_context: str | None
    prediction_date_key: str | None
    private_league_id: str | None
    user_id: str | None
    winner: str | None
    kickoff_date_key: str | None
    prediction_era: str | None
    result_date_key: str | None
    source_table: str | None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> PredictionsRow:
        """Normalize a raw warehouse row into a typed PredictionsRow."""
        return cls(
            unified_prediction_id=normalize_string_id(row["unified_prediction_id"], field_name="unified_prediction_id"),
            prediction_id=normalize_nullable_string_id(row.get("prediction_id"), field_name="prediction_id"),
            actual_score=row.get("actual_score"),
            fixture_id=normalize_nullable_string_id(row.get("fixture_id"), field_name="fixture_id"),
            influencer_league_id=normalize_nullable_string_id(row.get("influencer_league_id"), field_name="influencer_league_id"),
            is_correct_result=int(row["is_correct_result"]) if row.get("is_correct_result") is not None else None,
            is_correct_score=int(row["is_correct_score"]) if row.get("is_correct_score") is not None else None,
            is_processed=int(row["is_processed"]) if row.get("is_processed") is not None else None,
            kickoff_at_utc=warehouse_value_to_utc_datetime(row.get("kickoff_at_utc")),
            league_id=int(row["league_id"]) if row.get("league_id") is not None else None,
            points_awarded=float(row["points_awarded"]) if row.get("points_awarded") is not None else None,
            predicted_at_utc=warehouse_value_to_utc_datetime(row.get("predicted_at_utc")),
            predicted_outcome=row.get("predicted_outcome"),
            predicted_score=row.get("predicted_score"),
            prediction_context=row.get("prediction_context"),
            prediction_date_key=str(row["prediction_date_key"]) if row.get("prediction_date_key") is not None else None,
            private_league_id=normalize_nullable_string_id(row.get("private_league_id"), field_name="private_league_id"),
            user_id=normalize_nullable_string_id(row.get("user_id"), field_name="user_id"),
            winner=row.get("winner"),
            kickoff_date_key=str(row["kickoff_date_key"]) if row.get("kickoff_date_key") is not None else None,
            prediction_era=row.get("prediction_era"),
            result_date_key=str(row["result_date_key"]) if row.get("result_date_key") is not None else None,
            source_table=row.get("source_table"),
        )
