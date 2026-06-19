"""
Warehouse schema for dim_questions.

Source table: dim_questions
Domain: engagement
Inclusion mode: GRAPH_CORE — direct graph node creation
Graph entity: Question
Freshness field: created_at_utc

Core question catalog. Feeds Question nodes. dim_questions_enhanced enriches
these nodes with response analytics via GRAPH_ENRICHMENT.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.core.constants import GRAPH_CORE, QUESTION
from app.core.ids import normalize_string_id
from app.core.time import warehouse_value_to_utc_datetime

# ── Module-level constants ────────────────────────────────────────────────────

SOURCE_NAME: str = "dim_questions"
INCLUSION_MODE: str = GRAPH_CORE
PRIMARY_KEYS: tuple[str, ...] = ("question_id",)
FRESHNESS_FIELD: str | None = "created_at_utc"
GRAPH_ENTITY_MAPPINGS: tuple[str, ...] = (QUESTION,)


# ── Row shape ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class QuestionsRow:
    """
    Typed row shape for dim_questions.

    question_id is INTEGER PK; kept as int.
    created_at_utc is TIMESTAMP in the DWH.
    """

    question_id: int
    question_text: str | None
    created_at_utc: datetime | None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> QuestionsRow:
        """Normalize a raw warehouse row into a typed QuestionsRow."""
        return cls(
            question_id=int(normalize_string_id(row["question_id"], field_name="question_id")),
            question_text=row.get("question_text"),
            created_at_utc=warehouse_value_to_utc_datetime(row.get("created_at_utc")),
        )
