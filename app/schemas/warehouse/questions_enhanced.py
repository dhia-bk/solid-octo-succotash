"""
Warehouse schema for dim_questions_enhanced.

Source table: dim_questions_enhanced
Domain: engagement
Inclusion mode: GRAPH_ENRICHMENT — enriches existing Question nodes
Graph entity: Question (enrichment; adds engagement analytics)
Freshness field: last_response_at_utc

Adds response distribution and timing analytics to existing Question nodes.
Shares question_id PK with dim_questions.

DWH type notes:
    start_datetime_utc, end_datetime_utc,
    first_response_at_utc, last_response_at_utc — VARCHAR(255) in DWH
        (ISO strings, not native DATETIME columns); normalized via
        warehouse_value_to_utc_datetime which handles string input safely.
    is_active     — INTEGER in DWH (not TINYINT); int | None.
    duration_hours — INTEGER in DWH (not float as spec suggested); int | None.
    yes/no_percentage, avg_response_time_minutes — DOUBLE; float | None.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.core.constants import GRAPH_ENRICHMENT, QUESTION
from app.core.ids import normalize_string_id
from app.core.time import warehouse_value_to_utc_datetime

# ── Module-level constants ────────────────────────────────────────────────────

SOURCE_NAME: str = "dim_questions_enhanced"
INCLUSION_MODE: str = GRAPH_ENRICHMENT
PRIMARY_KEYS: tuple[str, ...] = ("question_id",)
FRESHNESS_FIELD: str | None = "last_response_at_utc"
GRAPH_ENTITY_MAPPINGS: tuple[str, ...] = (QUESTION,)


# ── Row shape ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class QuestionsEnhancedRow:
    """
    Typed row shape for dim_questions_enhanced.

    is_active is INTEGER in the DWH (not TINYINT); int | None.
    duration_hours is INTEGER in the DWH (not float); int | None.

    start_datetime_utc, end_datetime_utc, first_response_at_utc, and
    last_response_at_utc are VARCHAR(255) in the DWH (ISO strings);
    normalized to datetime | None via warehouse_value_to_utc_datetime.
    """

    question_id: int
    question_title: str | None
    question_image: str | None
    start_datetime_utc: datetime | None
    end_datetime_utc: datetime | None
    is_active: int | None
    duration_hours: int | None
    total_responses: int | None
    unique_respondents: int | None
    yes_count: int | None
    no_count: int | None
    yes_percentage: float | None
    no_percentage: float | None
    first_response_at_utc: datetime | None
    last_response_at_utc: datetime | None
    avg_response_time_minutes: float | None
    responses_in_first_hour: int | None
    responses_in_first_day: int | None
    top_responding_country: str | None
    top_responding_gender: str | None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> QuestionsEnhancedRow:
        """Normalize a raw warehouse row into a typed QuestionsEnhancedRow."""
        return cls(
            question_id=int(normalize_string_id(row["question_id"], field_name="question_id")),
            question_title=row.get("question_title"),
            question_image=row.get("question_image"),
            start_datetime_utc=warehouse_value_to_utc_datetime(row.get("start_datetime_utc")),
            end_datetime_utc=warehouse_value_to_utc_datetime(row.get("end_datetime_utc")),
            is_active=int(row["is_active"]) if row.get("is_active") is not None else None,
            duration_hours=int(row["duration_hours"]) if row.get("duration_hours") is not None else None,
            total_responses=int(row["total_responses"]) if row.get("total_responses") is not None else None,
            unique_respondents=int(row["unique_respondents"]) if row.get("unique_respondents") is not None else None,
            yes_count=int(row["yes_count"]) if row.get("yes_count") is not None else None,
            no_count=int(row["no_count"]) if row.get("no_count") is not None else None,
            yes_percentage=float(row["yes_percentage"]) if row.get("yes_percentage") is not None else None,
            no_percentage=float(row["no_percentage"]) if row.get("no_percentage") is not None else None,
            first_response_at_utc=warehouse_value_to_utc_datetime(row.get("first_response_at_utc")),
            last_response_at_utc=warehouse_value_to_utc_datetime(row.get("last_response_at_utc")),
            avg_response_time_minutes=float(row["avg_response_time_minutes"]) if row.get("avg_response_time_minutes") is not None else None,
            responses_in_first_hour=int(row["responses_in_first_hour"]) if row.get("responses_in_first_hour") is not None else None,
            responses_in_first_day=int(row["responses_in_first_day"]) if row.get("responses_in_first_day") is not None else None,
            top_responding_country=row.get("top_responding_country"),
            top_responding_gender=row.get("top_responding_gender"),
        )
