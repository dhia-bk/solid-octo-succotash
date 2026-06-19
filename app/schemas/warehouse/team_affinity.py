"""
Warehouse schema for fct_team_affinity.

Source table: fct_team_affinity
Domain: intelligence
Inclusion mode: GRAPH_CORE — feeds relationship creation
Graph entity: HAS_AFFINITY relationship (User → Team)
Freshness field: calculated_at_utc

Computed user-to-team affinity scores. Feeds HAS_AFFINITY edge properties:
affinity type, prediction accuracy, engagement frequency, active fan flag.

DWH type notes:
    affinity_id            — VARCHAR(100) in DWH; stored as str (spec
                             suggested int, DWH wins).
    team_id                — VARCHAR(100) in DWH; str | None.
    prediction_accuracy_rate — DECIMAL(5,2); float | None.
    total_points_earned    — DECIMAL(10,2); float | None.
    first/last_prediction_date — DATE in DWH; stored as str | None
                             (date-only values; not converted to datetime
                             to avoid spurious timezone shifts).
    is_favorite_team, is_active_fan, is_local_fan — TINYINT 0/1 flags.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.core.constants import GRAPH_CORE, HAS_AFFINITY
from app.core.ids import normalize_nullable_string_id, normalize_string_id
from app.core.time import warehouse_value_to_utc_datetime

# ── Module-level constants ────────────────────────────────────────────────────

SOURCE_NAME: str = "fct_team_affinity"
INCLUSION_MODE: str = GRAPH_CORE
PRIMARY_KEYS: tuple[str, ...] = ("affinity_id",)
FRESHNESS_FIELD: str | None = "calculated_at_utc"
GRAPH_ENTITY_MAPPINGS: tuple[str, ...] = (HAS_AFFINITY,)


# ── Row shape ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class TeamAffinityRow:
    """
    Typed row shape for fct_team_affinity.

    TINYINT fields (0/1 integers, not booleans in the DWH):
        is_favorite_team
        is_active_fan
        is_local_fan

    affinity_id and team_id are VARCHAR in the DWH; stored as str / str | None.
    first_prediction_date and last_prediction_date are DATE columns; stored
    as str | None to preserve date-only semantics without timezone coercion.
    """

    affinity_id: str
    user_id: str | None
    team_id: str | None
    team_name: str | None
    is_favorite_team: int | None
    affinity_type: str | None
    total_predictions: int | None
    correct_predictions: int | None
    prediction_accuracy_rate: float | None
    total_points_earned: float | None
    posts_mentioning_team: int | None
    comments_mentioning_team: int | None
    first_prediction_date: str | None
    last_prediction_date: str | None
    days_since_last_prediction: int | None
    is_active_fan: int | None
    engagement_frequency: str | None
    prediction_bias: str | None
    user_country: str | None
    team_country: str | None
    is_local_fan: int | None
    calculated_at_utc: datetime | None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> TeamAffinityRow:
        """Normalize a raw warehouse row into a typed TeamAffinityRow."""
        return cls(
            affinity_id=normalize_string_id(row["affinity_id"], field_name="affinity_id"),
            user_id=normalize_nullable_string_id(row.get("user_id"), field_name="user_id"),
            team_id=normalize_nullable_string_id(row.get("team_id"), field_name="team_id"),
            team_name=row.get("team_name"),
            is_favorite_team=int(row["is_favorite_team"]) if row.get("is_favorite_team") is not None else None,
            affinity_type=row.get("affinity_type"),
            total_predictions=int(row["total_predictions"]) if row.get("total_predictions") is not None else None,
            correct_predictions=int(row["correct_predictions"]) if row.get("correct_predictions") is not None else None,
            prediction_accuracy_rate=float(row["prediction_accuracy_rate"]) if row.get("prediction_accuracy_rate") is not None else None,
            total_points_earned=float(row["total_points_earned"]) if row.get("total_points_earned") is not None else None,
            posts_mentioning_team=int(row["posts_mentioning_team"]) if row.get("posts_mentioning_team") is not None else None,
            comments_mentioning_team=int(row["comments_mentioning_team"]) if row.get("comments_mentioning_team") is not None else None,
            first_prediction_date=str(row["first_prediction_date"]) if row.get("first_prediction_date") is not None else None,
            last_prediction_date=str(row["last_prediction_date"]) if row.get("last_prediction_date") is not None else None,
            days_since_last_prediction=int(row["days_since_last_prediction"]) if row.get("days_since_last_prediction") is not None else None,
            is_active_fan=int(row["is_active_fan"]) if row.get("is_active_fan") is not None else None,
            engagement_frequency=row.get("engagement_frequency"),
            prediction_bias=row.get("prediction_bias"),
            user_country=row.get("user_country"),
            team_country=row.get("team_country"),
            is_local_fan=int(row["is_local_fan"]) if row.get("is_local_fan") is not None else None,
            calculated_at_utc=warehouse_value_to_utc_datetime(row.get("calculated_at_utc")),
        )
