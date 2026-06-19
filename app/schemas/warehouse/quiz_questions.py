"""
Warehouse schema for dim_quiz_questions_enhanced.

Source table: dim_quiz_questions_enhanced
Domain: engagement
Inclusion mode: GRAPH_CORE — direct graph node creation
Graph entity: QuizQuestion
Freshness field: created_at_utc

Quiz question catalog with embedded performance analytics. Feeds QuizQuestion
nodes and the HAS_QUESTION relationship (Quiz → QuizQuestion).

DWH type notes:
    created_at_utc, scheduled_date_utc,
    first_answer_at_utc, last_answer_at_utc — VARCHAR(255) in DWH
        (ISO strings, not native DATETIME columns); normalized via
        warehouse_value_to_utc_datetime which handles string input safely.
    is_active         — INTEGER in DWH (not TINYINT); int | None.
    points_awarded_total — INTEGER in DWH; int | None.
    accuracy_rate, avg_points_per_attempt — DOUBLE; float | None.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.core.constants import GRAPH_CORE, QUIZ_QUESTION
from app.core.ids import normalize_nullable_string_id, normalize_string_id
from app.core.time import warehouse_value_to_utc_datetime

# ── Module-level constants ────────────────────────────────────────────────────

SOURCE_NAME: str = "dim_quiz_questions_enhanced"
INCLUSION_MODE: str = GRAPH_CORE
PRIMARY_KEYS: tuple[str, ...] = ("quiz_question_id",)
FRESHNESS_FIELD: str | None = "last_answer_at_utc"
GRAPH_ENTITY_MAPPINGS: tuple[str, ...] = (QUIZ_QUESTION,)


# ── Row shape ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class QuizQuestionsRow:
    """
    Typed row shape for dim_quiz_questions_enhanced.

    is_active is INTEGER in the DWH (not TINYINT); int | None.
    points_awarded_total is INTEGER; int | None.

    created_at_utc, scheduled_date_utc, first_answer_at_utc, and
    last_answer_at_utc are VARCHAR(255) in the DWH (ISO strings);
    normalized to datetime | None via warehouse_value_to_utc_datetime.
    """

    quiz_question_id: int
    creator_user_id: str | None
    question_text: str | None
    option1: str | None
    option2: str | None
    option3: str | None
    option4: str | None
    correct_option: int | None
    total_attempts: int | None
    correct_attempts: int | None
    wrong_attempts: int | None
    accuracy_rate: float | None
    difficulty_level: str | None
    option1_selected_count: int | None
    option2_selected_count: int | None
    option3_selected_count: int | None
    option4_selected_count: int | None
    unique_users_attempted: int | None
    points_awarded_total: int | None
    avg_points_per_attempt: float | None
    created_at_utc: datetime | None
    scheduled_date_utc: datetime | None
    first_answer_at_utc: datetime | None
    last_answer_at_utc: datetime | None
    is_active: int | None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> QuizQuestionsRow:
        """Normalize a raw warehouse row into a typed QuizQuestionsRow."""
        return cls(
            quiz_question_id=int(normalize_string_id(row["quiz_question_id"], field_name="quiz_question_id")),
            creator_user_id=normalize_nullable_string_id(row.get("creator_user_id"), field_name="creator_user_id"),
            question_text=row.get("question_text"),
            option1=row.get("option1"),
            option2=row.get("option2"),
            option3=row.get("option3"),
            option4=row.get("option4"),
            correct_option=int(row["correct_option"]) if row.get("correct_option") is not None else None,
            total_attempts=int(row["total_attempts"]) if row.get("total_attempts") is not None else None,
            correct_attempts=int(row["correct_attempts"]) if row.get("correct_attempts") is not None else None,
            wrong_attempts=int(row["wrong_attempts"]) if row.get("wrong_attempts") is not None else None,
            accuracy_rate=float(row["accuracy_rate"]) if row.get("accuracy_rate") is not None else None,
            difficulty_level=row.get("difficulty_level"),
            option1_selected_count=int(row["option1_selected_count"]) if row.get("option1_selected_count") is not None else None,
            option2_selected_count=int(row["option2_selected_count"]) if row.get("option2_selected_count") is not None else None,
            option3_selected_count=int(row["option3_selected_count"]) if row.get("option3_selected_count") is not None else None,
            option4_selected_count=int(row["option4_selected_count"]) if row.get("option4_selected_count") is not None else None,
            unique_users_attempted=int(row["unique_users_attempted"]) if row.get("unique_users_attempted") is not None else None,
            points_awarded_total=int(row["points_awarded_total"]) if row.get("points_awarded_total") is not None else None,
            avg_points_per_attempt=float(row["avg_points_per_attempt"]) if row.get("avg_points_per_attempt") is not None else None,
            created_at_utc=warehouse_value_to_utc_datetime(row.get("created_at_utc")),
            scheduled_date_utc=warehouse_value_to_utc_datetime(row.get("scheduled_date_utc")),
            first_answer_at_utc=warehouse_value_to_utc_datetime(row.get("first_answer_at_utc")),
            last_answer_at_utc=warehouse_value_to_utc_datetime(row.get("last_answer_at_utc")),
            is_active=int(row["is_active"]) if row.get("is_active") is not None else None,
        )
