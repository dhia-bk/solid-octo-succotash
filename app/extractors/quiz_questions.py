"""
Extractor for the dim_quiz_questions_enhanced warehouse source.

Purpose:
- Extract quiz question rows from dim_quiz_questions_enhanced, including
  question content, answer options, correct option, embedded performance
  analytics (attempts, accuracy, option distributions, points), and
  activity timestamps.
- Incremental strategy using last_answer_at_utc as the watermark.
- Return typed QuizQuestionsRow instances wrapped in ExtractorBatch.

Watermark field — last_answer_at_utc:
    last_answer_at_utc is used as the incremental field for this source

Nullable analytics fields:
    All performance analytics fields are NULL for questions that have never
    been answered. Extracted faithfully as NULL; the transformer must treat
    NULL as "no activity yet" rather than zero.

Nullable creator field:
    creator_user_id is NULL for questions with no declared creator.
    Extracted faithfully; the transformer gates creator-edge creation on
    non-NULL values.

Design rules:
- quiz_question_id is an integer PK; used as the sole ordering field for
  deterministic extraction.
- last_answer_at_utc is VARCHAR(255) in the DWH; string ISO 8601 comparison
  for watermark filtering is safe with consistent UTC formatting.
- No graph logic, canonicalization, or enrichment is applied here.
- Deduplication is a transformer concern; the extractor emits rows as
  received from the warehouse.

Source schema:
- Source table  : dim_quiz_questions_enhanced
- Inclusion mode: GRAPH_CORE
- Graph entity  : QuizQuestion
- Freshness field (schema): created_at_utc
- Freshness field (extractor): last_answer_at_utc — see watermark note above
- Declared PK   : quiz_question_id
"""

from __future__ import annotations

from app.contracts.warehouse_rows import WarehouseRow
from app.extractors.base import BaseExtractor
from app.schemas.warehouse.quiz_questions import (
    INCLUSION_MODE,
    PRIMARY_KEYS,
    SOURCE_NAME,
    FRESHNESS_FIELD,
    QuizQuestionsRow,
)




class QuizQuestionsExtractor(BaseExtractor):
    """
    Extractor for dim_quiz_questions_enhanced.

    Incremental strategy:
    - watermark field: last_answer_at_utc (VARCHAR(255) ISO string in DWH)
    - ordering: quiz_question_id

    Analytics mutation coverage:
    - Embedded performance analytics (attempts, accuracy, option counts,
      points) accumulate post-creation. last_answer_at_utc advances with
      each new answer event, ensuring updated analytics are captured
      incrementally. created_at_utc (schema FRESHNESS_FIELD) is intentionally
      not used here — it would miss all post-creation mutations.

    Bootstrap behaviour:
    - On first run (watermark is None), a full-table load is performed.
      Questions with NULL last_answer_at_utc (never answered) are included
      in the bootstrap and correctly excluded from subsequent incremental
      runs as their watermark field remains NULL.

    Nullable analytics fields:
    - All performance analytics are NULL for unanswered questions. Extracted
      faithfully; transformer treats NULL as no activity data.

    Nullable creator field:
    - creator_user_id is NULL for questions with no declared creator.
      Preserved as NULL; transformer gates creator-edge creation on
      non-NULL values.
    """

    source_name: str = SOURCE_NAME
    schema_row_class: type[WarehouseRow] = QuizQuestionsRow
    inclusion_mode: str = INCLUSION_MODE
    freshness_field: str | None = FRESHNESS_FIELD      # last_answer_at_utc
    primary_key_fields: tuple[str, ...] = PRIMARY_KEYS
    default_chunk_size: int = 1000
    supports_incremental: bool = True

    # ── Source column contract ────────────────────────────────────────────────

    def get_source_columns(self) -> tuple[str, ...]:
        """
        Return the explicit ordered source columns for dim_quiz_questions_enhanced.

        These columns must stay aligned with QuizQuestionsRow.from_row().
        Adding or removing a column here requires a matching change in
        the schema row dataclass.

        DWH type notes:
            created_at_utc, scheduled_date_utc,
            first_answer_at_utc, last_answer_at_utc — VARCHAR(255) ISO
                strings in the DWH; normalized to datetime | None by
                warehouse_value_to_utc_datetime in the row dataclass.
            is_active            — INTEGER (not TINYINT); coerced to int | None.
            points_awarded_total — INTEGER; coerced to int | None.
            accuracy_rate, avg_points_per_attempt — DOUBLE; coerced to float | None.

        Nullable analytics fields note:
            total_attempts, correct_attempts, wrong_attempts, accuracy_rate,
            option*_selected_count, unique_users_attempted, points_awarded_total,
            avg_points_per_attempt, first_answer_at_utc, last_answer_at_utc —
            all NULL for questions that have never been answered. Preserved
            as NULL; transformer treats NULL as no activity data.

        Watermark field note:
            last_answer_at_utc is the extractor watermark (overrides schema
            FRESHNESS_FIELD = created_at_utc). VARCHAR(255) ISO string;
            string-based comparison is monotonically correct for UTC timestamps.
        """
        return (
            "quiz_question_id",
            "creator_user_id",              # nullable string FK — NULL if no creator declared
            "question_text",
            "option1",
            "option2",
            "option3",
            "option4",
            "correct_option",
            "total_attempts",               # NULL if never answered
            "correct_attempts",             # NULL if never answered
            "wrong_attempts",               # NULL if never answered
            "accuracy_rate",                # DOUBLE; NULL if never answered
            "difficulty_level",
            "option1_selected_count",       # NULL if never answered
            "option2_selected_count",       # NULL if never answered
            "option3_selected_count",       # NULL if never answered
            "option4_selected_count",       # NULL if never answered
            "unique_users_attempted",       # NULL if never answered
            "points_awarded_total",         # INTEGER in DWH; NULL if never answered
            "avg_points_per_attempt",       # DOUBLE; NULL if never answered
            "created_at_utc",               # VARCHAR(255) ISO string in DWH
            "scheduled_date_utc",           # VARCHAR(255) ISO string in DWH
            "first_answer_at_utc",          # VARCHAR(255) ISO string; NULL if never answered
            "last_answer_at_utc",           # VARCHAR(255); extractor watermark field
            "is_active",                    # INTEGER in DWH (not TINYINT)
        )

    # ── Query construction ────────────────────────────────────────────────────

    def build_base_query(self) -> str:
        """
        Return the base SELECT for dim_quiz_questions_enhanced without
        incremental filtering.

        The incremental clause
        (WHERE last_answer_at_utc > :watermark_value) is appended by the
        base runtime via build_incremental_clause().
        """
        columns = ",\n    ".join(self.get_source_columns())
        return f"""
SELECT
    {columns}
FROM {self.source_name}
""".strip()

    def build_incremental_clause(self, watermark_value: str | None) -> str:
        """
        Build the incremental filter using last_answer_at_utc.

        Uses strict greater-than semantics so watermark advancement remains
        monotonic across runs. String-based ISO 8601 comparison on
        last_answer_at_utc is correct for consistently formatted UTC
        timestamps stored as VARCHAR(255) in the DWH.

        Questions with NULL last_answer_at_utc (never answered) will never
        satisfy this clause and are correctly excluded from incremental runs
        after the bootstrap load.

        No clause is emitted on first run (watermark is None), triggering a
        full-table bootstrap load that captures all rows including those with
        NULL last_answer_at_utc.
        """
        if not self.supports_incremental or not self.freshness_field:
            return ""

        if not watermark_value:
            return ""

        return f"\nWHERE {self.freshness_field} > :watermark_value"

    def build_order_by_clause(self) -> str:
        """
        Return stable deterministic ordering for dim_quiz_questions_enhanced.

        quiz_question_id only — integer PK; provides fully deterministic
        ordering across all rows. The watermark field (last_answer_at_utc)
        is VARCHAR(255) and NULL for unanswered questions; including it in
        ORDER BY would push NULL rows to an implementation-defined position
        and introduce collation edge cases. quiz_question_id alone is
        sufficient and unambiguous.
        """
        return "\nORDER BY quiz_question_id"

    def build_pagination_clause(self, limit: int, offset: int) -> str:
        """
        Return LIMIT/OFFSET pagination clause.
        """
        return "\nLIMIT %(limit)s OFFSET %(offset)s"