"""
Extractor for the dim_questions_enhanced warehouse source.

Purpose:
- Extract enriched question analytics from dim_questions_enhanced, including
  activity window (start/end), response totals, yes/no distributions,
  timing metrics, and demographic aggregates.
- Incremental strategy using last_response_at_utc as the watermark when
  available; falls back to full refresh on bootstrap (watermark is None).
- Return typed QuestionsEnhancedRow instances wrapped in ExtractorBatch.

Shared PK with dim_questions:
    dim_questions_enhanced shares question_id as its primary key with the
    dim_questions source. This extractor does not join or coordinate with
    dim_questions — it extracts the enrichment dimension independently.
    The transformer is responsible for merging enrichment properties onto
    existing Question graph nodes.

Watermark field — last_response_at_utc:
    last_response_at_utc is the correct incremental field for this source
    because it advances monotonically as new responses arrive. Rows that
    have accumulated additional responses since the last run will have an
    updated last_response_at_utc and will be captured by the incremental
    clause. Questions with no new responses since the watermark are
    correctly excluded.

    DWH type note: last_response_at_utc is stored as VARCHAR(255) (ISO
    string) in the warehouse, not a native DATETIME column. String-based
    ISO 8601 comparison is monotonically correct for UTC timestamps with
    consistent formatting; the watermark comparison remains valid.

Nullable analytics fields:
    All analytics fields (yes_count, no_count, percentages, timing metrics,
    demographic aggregates) are NULL for questions that have received no
    responses. They are extracted faithfully as NULL; the transformer
    must treat NULL as "no data yet" rather than zero.

Design rules:
- question_id is an integer PK shared with dim_questions; used as the
  ordering tiebreaker for deterministic extraction.
- last_response_at_utc is VARCHAR(255) in the DWH; extracted and passed
  as a string watermark. Comparison semantics remain correct for
  well-formed ISO UTC strings.
- No graph logic, enrichment merging, or property canonicalization here.
- Deduplication is a transformer concern; the extractor emits rows as
  received from the warehouse.

Source schema:
- Source table  : dim_questions_enhanced
- Inclusion mode: GRAPH_ENRICHMENT
- Graph entity  : Question (enrichment)
- Freshness field: last_response_at_utc
- Declared PK   : question_id (shared with dim_questions)
"""

from __future__ import annotations

from app.contracts.warehouse_rows import WarehouseRow
from app.extractors.base import BaseExtractor
from app.schemas.warehouse.questions_enhanced import (
    FRESHNESS_FIELD,
    INCLUSION_MODE,
    PRIMARY_KEYS,
    SOURCE_NAME,
    QuestionsEnhancedRow,
)


class QuestionsEnhancedExtractor(BaseExtractor):
    """
    Extractor for dim_questions_enhanced.

    Incremental strategy:
    - watermark field: last_response_at_utc (VARCHAR(255) ISO string in DWH)
    - ordering: question_id (stable integer PK; deterministic across runs)

    Bootstrap behaviour:
    - When watermark_value is None (first run), no incremental clause is
      emitted and a full-table load is performed. Subsequent runs filter
      strictly on last_response_at_utc > watermark_value.

    Nullable analytics fields:
    - All response counts, percentages, timing metrics, and demographic
      aggregates are NULL for questions with no responses. Extracted
      faithfully; transformer treats NULL as absence of engagement data.

    Shared PK:
    - question_id is shared with dim_questions. The extractor does not
      coordinate with dim_questions — enrichment merging is a transformer
      concern.
    """

    source_name: str = SOURCE_NAME
    schema_row_class: type[WarehouseRow] = QuestionsEnhancedRow
    inclusion_mode: str = INCLUSION_MODE
    freshness_field: str | None = FRESHNESS_FIELD       # last_response_at_utc
    primary_key_fields: tuple[str, ...] = PRIMARY_KEYS
    default_chunk_size: int = 1000
    supports_incremental: bool = True

    # ── Source column contract ────────────────────────────────────────────────

    def get_source_columns(self) -> tuple[str, ...]:
        """
        Return the explicit ordered source columns for dim_questions_enhanced.

        These columns must stay aligned with QuestionsEnhancedRow.from_row().
        Adding or removing a column here requires a matching change in
        the schema row dataclass.

        DWH type notes:
            start_datetime_utc, end_datetime_utc,
            first_response_at_utc, last_response_at_utc — VARCHAR(255) ISO
                strings in the DWH; normalized to datetime | None by
                warehouse_value_to_utc_datetime in the row dataclass.
            is_active     — INTEGER (not TINYINT); coerced to int | None.
            duration_hours — INTEGER (not float); coerced to int | None.
            yes_percentage, no_percentage,
            avg_response_time_minutes — DOUBLE; coerced to float | None.

        Nullable analytics fields note:
            yes_count, no_count, yes_percentage, no_percentage,
            avg_response_time_minutes, responses_in_first_hour,
            responses_in_first_day, top_responding_country,
            top_responding_gender — all NULL for questions with no responses.
            Preserved as NULL; transformer treats NULL as no engagement data.

        Watermark field note:
            last_response_at_utc is the incremental watermark and is stored
            as VARCHAR(255); string-based ISO 8601 comparison is monotonically
            correct for UTC timestamps with consistent formatting.
        """
        return (
            "question_id",
            "question_title",
            "question_image",
            "start_datetime_utc",           # VARCHAR(255) ISO string in DWH
            "end_datetime_utc",             # VARCHAR(255) ISO string in DWH
            "is_active",                    # INTEGER in DWH (not TINYINT)
            "duration_hours",               # INTEGER in DWH (not float)
            "total_responses",
            "unique_respondents",
            "yes_count",                    # NULL if no responses yet
            "no_count",                     # NULL if no responses yet
            "yes_percentage",               # DOUBLE; NULL if no responses yet
            "no_percentage",                # DOUBLE; NULL if no responses yet
            "first_response_at_utc",        # VARCHAR(255) ISO string in DWH
            "last_response_at_utc",         # VARCHAR(255); extractor watermark field
            "avg_response_time_minutes",    # DOUBLE; NULL if no responses yet
            "responses_in_first_hour",      # NULL if no responses yet
            "responses_in_first_day",       # NULL if no responses yet
            "top_responding_country",       # NULL if no responses yet
            "top_responding_gender",        # NULL if no responses yet
        )

    # ── Query construction ────────────────────────────────────────────────────

    def build_base_query(self) -> str:
        """
        Return the base SELECT for dim_questions_enhanced without incremental
        filtering.

        The incremental clause (WHERE last_response_at_utc > :watermark_value)
        is appended by the base runtime via build_incremental_clause().
        """
        columns = ",\n    ".join(self.get_source_columns())
        return f"""
SELECT
    {columns}
FROM {self.source_name}
""".strip()

    def build_incremental_clause(self, watermark_value: str | None) -> str:
        """
        Build the incremental filter using last_response_at_utc.

        Uses strict greater-than semantics so watermark advancement remains
        monotonic across runs. String-based ISO 8601 comparison on
        last_response_at_utc is correct for consistently formatted UTC
        timestamps stored as VARCHAR(255) in the DWH.

        No clause is emitted on first run (watermark is None), triggering a
        full-table bootstrap load.
        """
        if not self.supports_incremental or not self.freshness_field:
            return ""

        if not watermark_value:
            return ""

        return f"\nWHERE {self.freshness_field} > :watermark_value"

    def build_order_by_clause(self) -> str:
        """
        Return stable deterministic ordering for dim_questions_enhanced.

        question_id only — integer PK shared with dim_questions; provides
        fully deterministic ordering across all rows regardless of
        last_response_at_utc value. The watermark field is VARCHAR(255) in
        the DWH; including it in ORDER BY alongside an integer PK adds no
        disambiguation value and risks non-determinism from string collation
        edge cases.
        """
        return "\nORDER BY question_id"

    def build_pagination_clause(self, limit: int, offset: int) -> str:
        """
        Return LIMIT/OFFSET pagination clause.
        """
        return "\nLIMIT %(limit)s OFFSET %(offset)s"