"""
Extractor for the dim_quizzes warehouse source.

Purpose:
- Extract quiz catalog rows from dim_quizzes, including identity, creator
  linkage, scheduling, question count, and active status.
- Incremental strategy using created_at_utc as the watermark.
- Return typed QuizzesRow instances wrapped in ExtractorBatch.

Watermark field — created_at_utc:
    created_at_utc is the correct incremental field for this source because
    dim_quizzes is an append-dominant catalog — quizzes are created, not
    mutated through a multi-stage lifecycle. New quizzes always carry a
    created_at_utc beyond the previous watermark, ensuring incremental runs
    capture all newly created quiz nodes without rescanning existing rows.

    Note: if is_active or total_questions can mutate post-creation without
    advancing created_at_utc, those updates will not be captured
    incrementally. A full-refresh run or a secondary updated_at_utc field
    would be required to cover that case. This extractor follows the declared
    freshness field in the schema (created_at_utc) as-is.

Design rules:
- quiz_id is an integer PK; used as the ordering tiebreaker.
- creator_user_id is a nullable string FK; extracted faithfully as NULL when
  absent — the transformer gates creator-edge creation on non-NULL values.
- is_active is TINYINT 0/1 in the DWH; extracted as int | None, not bool.
- scheduled_date is a TIMESTAMP in the DWH; normalized to datetime | None.
- No graph logic, canonicalization, or enrichment is applied here.

Source schema:
- Source table  : dim_quizzes
- Inclusion mode: GRAPH_CORE
- Graph entity  : Quiz
- Freshness field: created_at_utc
- Declared PK   : quiz_id
"""

from __future__ import annotations

from app.contracts.warehouse_rows import WarehouseRow
from app.extractors.base import BaseExtractor
from app.schemas.warehouse.quizzes import (
    FRESHNESS_FIELD,
    INCLUSION_MODE,
    PRIMARY_KEYS,
    SOURCE_NAME,
    QuizzesRow,
)


class QuizzesExtractor(BaseExtractor):
    """
    Extractor for dim_quizzes.

    Incremental strategy:
    - watermark field: created_at_utc
    - ordering: created_at_utc, quiz_id

    Append-dominant source:
    - dim_quizzes is a quiz catalog where rows are created, not mutated
      through lifecycle stages. created_at_utc therefore reliably captures
      all new quiz nodes in incremental runs.

    Nullable creator field:
    - creator_user_id is NULL for quizzes with no declared creator.
      Extracted faithfully; transformer gates creator-edge creation on
      non-NULL values.
    """

    source_name: str = SOURCE_NAME
    schema_row_class: type[WarehouseRow] = QuizzesRow
    inclusion_mode: str = INCLUSION_MODE
    freshness_field: str | None = FRESHNESS_FIELD       # created_at_utc
    primary_key_fields: tuple[str, ...] = PRIMARY_KEYS
    default_chunk_size: int = 1000
    supports_incremental: bool = True

    # ── Source column contract ────────────────────────────────────────────────

    def get_source_columns(self) -> tuple[str, ...]:
        """
        Return the explicit ordered source columns for dim_quizzes.

        These columns must stay aligned with QuizzesRow.from_row().
        Adding or removing a column here requires a matching change in
        the schema row dataclass.

        is_active note:
            TINYINT 0/1 in the DWH; coerced to int | None in the row
            dataclass. Not a Python bool.

        scheduled_date note:
            TIMESTAMP in the DWH; normalized to datetime | None via
            warehouse_value_to_utc_datetime.

        creator_user_id note:
            Nullable string FK. NULL for quizzes with no declared creator.
            Preserved as NULL; transformer gates creator-edge creation on
            non-NULL values.
        """
        return (
            "quiz_id",
            "quiz_name",
            "creator_user_id",      # nullable string FK — NULL if no creator declared
            "created_at_utc",       # extractor watermark field
            "scheduled_date",       # TIMESTAMP in DWH
            "total_questions",
            "is_active",            # TINYINT 0/1 in DWH (not bool)
        )

    # ── Query construction ────────────────────────────────────────────────────

    def build_base_query(self) -> str:
        """
        Return the base SELECT for dim_quizzes without incremental filtering.

        The incremental clause (WHERE created_at_utc > %(watermark_value)s)
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
        Build the incremental filter using created_at_utc.

        Uses strict greater-than semantics so watermark advancement remains
        monotonic across runs. Appropriate for an append-dominant source
        where rows are created but not mutated post-creation.

        No clause is emitted on first run (watermark is None), triggering a
        full-table bootstrap load.
        """
        if not self.supports_incremental or not self.freshness_field:
            return ""

        if not watermark_value:
            return ""

        return f"\nWHERE {self.freshness_field} > %(watermark_value)s"

    def build_order_by_clause(self) -> str:
        """
        Return stable deterministic ordering for dim_quizzes.

        created_at_utc first — aligns with watermark advancement and clusters
        output chronologically by quiz creation time.

        quiz_id second — integer PK; breaks ties within the same
        created_at_utc bucket deterministically.
        """
        return "\nORDER BY created_at_utc, quiz_id"

    def build_pagination_clause(self, limit: int, offset: int) -> str:
        """
        Return LIMIT/OFFSET pagination clause.
        """
        return "\nLIMIT %(limit)s OFFSET %(offset)s"