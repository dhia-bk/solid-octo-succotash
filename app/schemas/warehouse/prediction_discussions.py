"""
Warehouse schema for dim_prediction_discussions.

Source table: dim_prediction_discussions
Domain: social
Inclusion mode: GRAPH_CORE — direct graph node creation
Graph entity: PredictionDiscussion
Freshness field: created_at_utc

Prediction-specific discussion threads, distinct from fixture-level
discussions. Feeds ABOUT relationship (PredictionDiscussion → Match)
via the prediction context.

DWH type notes:
    prediction_discussion_id — INTEGER PK; stored as int.
    prediction_id            — INTEGER in DWH; normalized to str | None for
                               cross-entity consistency (prediction IDs are
                               referenced as strings in fct_predictions).
    created_at_utc           — TIMESTAMP in DWH.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.core.constants import GRAPH_CORE, PREDICTION_DISCUSSION
from app.core.ids import normalize_string_id
from app.core.time import warehouse_value_to_utc_datetime

# ── Module-level constants ────────────────────────────────────────────────────

SOURCE_NAME: str = "dim_prediction_discussions"
INCLUSION_MODE: str = GRAPH_CORE
PRIMARY_KEYS: tuple[str, ...] = ("prediction_discussion_id",)
FRESHNESS_FIELD: str | None = "created_at_utc"
GRAPH_ENTITY_MAPPINGS: tuple[str, ...] = (PREDICTION_DISCUSSION,)


# ── Row shape ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class PredictionDiscussionsRow:
    """
    Typed row shape for dim_prediction_discussions.

    prediction_id is INTEGER in the DWH but normalized to str | None
    for consistency with fct_predictions where prediction IDs are VARCHAR.
    """

    prediction_discussion_id: int
    created_at_utc: datetime | None
    discussion_type: str | None
    prediction_id: str | None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> PredictionDiscussionsRow:
        """Normalize a raw warehouse row into a typed PredictionDiscussionsRow."""
        return cls(
            prediction_discussion_id=int(normalize_string_id(
                row["prediction_discussion_id"], field_name="prediction_discussion_id"
            )),
            created_at_utc=warehouse_value_to_utc_datetime(row.get("created_at_utc")),
            discussion_type=row.get("discussion_type"),
            prediction_id=str(row["prediction_id"]) if row.get("prediction_id") is not None else None,
        )
