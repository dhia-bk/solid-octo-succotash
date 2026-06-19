"""
Warehouse schema for dim_fixture_polls_enhanced.

Source table: dim_fixture_polls_enhanced
Domain: engagement
Inclusion mode: GRAPH_CORE — direct graph node creation
Graph entity: Poll
Freshness field: created_at_utc

Fixture-linked poll dimension with engagement analytics. Feeds Poll nodes
linked to Match nodes via fixture_id.

DWH type notes:
    fixture_poll_id — VARCHAR(100) in DWH; str (spec suggested int).
    fixture_id      — VARCHAR(100) in DWH; str | None (spec suggested int).
    creator_user_id — VARCHAR(100) in DWH; str | None.
    is_active       — TINYINT 0/1.
    option1/2_percentage, avg_response_time_minutes — DOUBLE; float | None.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.core.constants import GRAPH_CORE, POLL
from app.core.ids import normalize_nullable_string_id, normalize_string_id
from app.core.time import warehouse_value_to_utc_datetime

# ── Module-level constants ────────────────────────────────────────────────────

SOURCE_NAME: str = "dim_fixture_polls_enhanced"
INCLUSION_MODE: str = GRAPH_CORE
PRIMARY_KEYS: tuple[str, ...] = ("fixture_poll_id",)
FRESHNESS_FIELD: str | None = "created_at_utc"
GRAPH_ENTITY_MAPPINGS: tuple[str, ...] = (POLL,)


# ── Row shape ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class FixturePollsRow:
    """
    Typed row shape for dim_fixture_polls_enhanced.

    TINYINT fields (0/1 integers, not booleans in the DWH):
        is_active

    fixture_poll_id and fixture_id are VARCHAR(100) in the DWH; stored as
    str / str | None.
    """

    fixture_poll_id: str
    fixture_id: str | None
    creator_user_id: str | None
    question_text: str | None
    option1: str | None
    option2: str | None
    created_at_utc: datetime | None
    is_active: int | None
    total_responses: int | None
    unique_respondents: int | None
    option1_count: int | None
    option2_count: int | None
    option1_percentage: float | None
    option2_percentage: float | None
    first_response_at_utc: datetime | None
    last_response_at_utc: datetime | None
    avg_response_time_minutes: float | None
    responses_in_first_hour: int | None
    responses_in_first_day: int | None
    top_responding_country: str | None
    top_responding_gender: str | None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> FixturePollsRow:
        """Normalize a raw warehouse row into a typed FixturePollsRow."""
        return cls(
            fixture_poll_id=normalize_string_id(row["fixture_poll_id"], field_name="fixture_poll_id"),
            fixture_id=normalize_nullable_string_id(row.get("fixture_id"), field_name="fixture_id"),
            creator_user_id=normalize_nullable_string_id(row.get("creator_user_id"), field_name="creator_user_id"),
            question_text=row.get("question_text"),
            option1=row.get("option1"),
            option2=row.get("option2"),
            created_at_utc=warehouse_value_to_utc_datetime(row.get("created_at_utc")),
            is_active=int(row["is_active"]) if row.get("is_active") is not None else None,
            total_responses=int(row["total_responses"]) if row.get("total_responses") is not None else None,
            unique_respondents=int(row["unique_respondents"]) if row.get("unique_respondents") is not None else None,
            option1_count=int(row["option1_count"]) if row.get("option1_count") is not None else None,
            option2_count=int(row["option2_count"]) if row.get("option2_count") is not None else None,
            option1_percentage=float(row["option1_percentage"]) if row.get("option1_percentage") is not None else None,
            option2_percentage=float(row["option2_percentage"]) if row.get("option2_percentage") is not None else None,
            first_response_at_utc=warehouse_value_to_utc_datetime(row.get("first_response_at_utc")),
            last_response_at_utc=warehouse_value_to_utc_datetime(row.get("last_response_at_utc")),
            avg_response_time_minutes=float(row["avg_response_time_minutes"]) if row.get("avg_response_time_minutes") is not None else None,
            responses_in_first_hour=int(row["responses_in_first_hour"]) if row.get("responses_in_first_hour") is not None else None,
            responses_in_first_day=int(row["responses_in_first_day"]) if row.get("responses_in_first_day") is not None else None,
            top_responding_country=row.get("top_responding_country"),
            top_responding_gender=row.get("top_responding_gender"),
        )
