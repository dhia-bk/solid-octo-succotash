"""
Extractor for the dim_questions warehouse source.

Purpose:
- Extract core question rows from dim_questions, including question_id,
  question text, and creation timestamp.
- Incremental strategy using created_at_utc as the watermark.
- Return typed QuestionsRow instances wrapped in ExtractorBatch.

Source characteristics:
    dim_questions is the identity catalog for platform questions. It is a
    lean three-column table — question_id, question_text, and created_at_utc.
    Response analytics and engagement enrichments live in dim_questions_enhanced
    (Step 42), which is a GRAPH_ENRICHMENT source layered on top of these
    Question nodes.

    Rows are created once when a question is authored and are not updated
    thereafter. Incremental extraction by created_at_utc is therefore
    complete and correct.

Design rules:
- question_id is an INTEGER PK; stored as int. Integer sort order is
  naturally correct without CAST.
- question_text is the raw question string; extracted faithfully — length
  enforcement is a loader concern.
- No graph logic, canonicalization, or enrichment is applied here.

Source schema:
- Source table  : dim_questions
- Inclusion mode: GRAPH_CORE
- Graph entity  : Question
- Freshness field: created_at_utc
"""

from __future__ import annotations

from app.contracts.warehouse_rows import WarehouseRow
from app.extractors.base import BaseExtractor
from app.schemas.warehouse.questions import (
    FRESHNESS_FIELD,
    INCLUSION_MODE,
    PRIMARY_KEYS,
    SOURCE_NAME,
    QuestionsRow,
)


class QuestionsExtractor(BaseExtractor):
    """
    Extractor for dim_questions.

    Incremental strategy:
    - watermark field: created_at_utc
    - ordering: created_at_utc, question_id

    Append-oriented semantics:
    - Questions are created once and not updated. Incremental extraction
      is therefore complete and correct with no mutation window required.

    Enrichment relationship:
    - dim_questions_enhanced (Step 42) enriches these Question nodes with
      response analytics. Both extractors must run for a complete Question
      node; this extractor provides identity, the enhanced extractor provides
      engagement metrics.
    """

    source_name: str = SOURCE_NAME
    schema_row_class: type[WarehouseRow] = QuestionsRow
    inclusion_mode: str = INCLUSION_MODE
    freshness_field: str | None = FRESHNESS_FIELD     # created_at_utc
    primary_key_fields: tuple[str, ...] = PRIMARY_KEYS
    default_chunk_size: int = 2000                    # questions catalog is
                                                      # bounded by editorial
                                                      # content production rate
    supports_incremental: bool = True

    # ── Source column contract ────────────────────────────────────────────────

    def get_source_columns(self) -> tuple[str, ...]:
        """
        Return the explicit ordered source columns for dim_questions.

        These columns must stay aligned with QuestionsRow.from_row().
        Adding or removing a column here requires a matching change in
        the schema row dataclass.
        """
        return (
            "question_id",
            "question_text",
            "created_at_utc",
        )

    # ── Query construction ────────────────────────────────────────────────────

    def build_base_query(self) -> str:
        """
        Return the base SELECT for dim_questions without incremental filtering.

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
        monotonic across runs. No clause is emitted on first run (watermark
        is None), triggering a full-table bootstrap load.
        """
        if not self.supports_incremental or not self.freshness_field:
            return ""

        if not watermark_value:
            return ""

        return f"\nWHERE {self.freshness_field} > %(watermark_value)s"

    def build_order_by_clause(self) -> str:
        """
        Return stable deterministic ordering for dim_questions.

        created_at_utc first — aligns with watermark advancement.

        question_id second — integer PK; breaks ties within the same
        creation timestamp bucket deterministically. Integer sort order
        is naturally correct without CAST.
        """
        return "\nORDER BY created_at_utc, question_id"

    def build_pagination_clause(self, limit: int, offset: int) -> str:
        """
        Return LIMIT/OFFSET pagination clause.
        """
        return "\nLIMIT %(limit)s OFFSET %(offset)s"