"""
Warehouse schema for dim_quizzes.

Source table: dim_quizzes
Domain: engagement
Inclusion mode: GRAPH_CORE — direct graph node creation
Graph entity: Quiz
Freshness field: created_at_utc

Quiz catalog. Feeds Quiz nodes and the HAS_QUESTION relationship pattern
(Quiz → QuizQuestion). is_active is TINYINT 0/1.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.core.constants import GRAPH_CORE, QUIZ
from app.core.ids import normalize_nullable_string_id, normalize_string_id
from app.core.time import warehouse_value_to_utc_datetime

# ── Module-level constants ────────────────────────────────────────────────────

SOURCE_NAME: str = "dim_quizzes"
INCLUSION_MODE: str = GRAPH_CORE
PRIMARY_KEYS: tuple[str, ...] = ("quiz_id",)
FRESHNESS_FIELD: str | None = "created_at_utc"
GRAPH_ENTITY_MAPPINGS: tuple[str, ...] = (QUIZ,)


# ── Row shape ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class QuizzesRow:
    """
    Typed row shape for dim_quizzes.

    TINYINT fields (0/1 integers, not booleans in the DWH):
        is_active

    scheduled_date is TIMESTAMP in the DWH.
    """

    quiz_id: int
    quiz_name: str | None
    creator_user_id: str | None
    created_at_utc: datetime | None
    scheduled_date: datetime | None
    total_questions: int | None
    is_active: int | None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> QuizzesRow:
        """Normalize a raw warehouse row into a typed QuizzesRow."""
        return cls(
            quiz_id=int(normalize_string_id(row["quiz_id"], field_name="quiz_id")),
            quiz_name=row.get("quiz_name"),
            creator_user_id=normalize_nullable_string_id(row.get("creator_user_id"), field_name="creator_user_id"),
            created_at_utc=warehouse_value_to_utc_datetime(row.get("created_at_utc")),
            scheduled_date=warehouse_value_to_utc_datetime(row.get("scheduled_date")),
            total_questions=int(row["total_questions"]) if row.get("total_questions") is not None else None,
            is_active=int(row["is_active"]) if row.get("is_active") is not None else None,
        )
