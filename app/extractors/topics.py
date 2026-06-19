"""
Extractor for the fct_topics warehouse source.

Purpose:
- Extract ML-derived topic labels from fct_topics, including source_type,
  item_id, user_id, topic_label, reasoning, and processing metadata.
- Incremental strategy using processed_at as the watermark.
- Return typed TopicsRow instances wrapped in ExtractorBatch.

Source characteristics:
    fct_topics is an append-oriented ML output table. Each row represents
    a topic classification produced by the ML pipeline for a single content
    item (post, comment, discussion, etc.) attributed to a user. Rows are
    written once when the ML pipeline processes the item; processed_at
    is the processing completion timestamp.

    Incremental extraction by processed_at captures all topic assignments
    produced since the last pipeline run without re-processing the full
    ML output history.

    item_id and source_type together identify the classified content entity.
    Both must be preserved exactly; downstream Topic node construction and
    DISCUSSED edge attribution depend on this composite identity.

Design rules:
- id is an INTEGER surrogate PK; stored as int and used as the ordering
  tiebreaker within the same processed_at bucket.
- item_id and user_id are VARCHAR in the DWH; preserved as str | None.
- source_type, item_id, and user_id form the composite content-entity
  identity. The extractor must not drop any of these fields.
- reasoning may contain free-text ML output of arbitrary length; extracted
  faithfully, storage truncation is a loader concern not an extractor concern.
- model_provider and model_version are provenance fields needed for
  downstream ML lineage tracking; both must be preserved.
- No graph logic, canonicalization, or enrichment is applied here.

Source schema:
- Source table  : fct_topics
- Inclusion mode: GRAPH_CORE
- Graph entity  : Topic
- Freshness field: processed_at
"""

from __future__ import annotations

from app.contracts.warehouse_rows import WarehouseRow
from app.extractors.base import BaseExtractor
from app.schemas.warehouse.topics import (
    FRESHNESS_FIELD,
    INCLUSION_MODE,
    PRIMARY_KEYS,
    SOURCE_NAME,
    TopicsRow,
)


class TopicsExtractor(BaseExtractor):
    """
    Extractor for fct_topics.

    Incremental strategy:
    - watermark field: processed_at
    - ordering: processed_at, id

    Append-oriented semantics:
    - Rows are written once by the ML pipeline; they are not updated after
      initial insertion. Incremental extraction by processed_at is therefore
      both correct and complete — no mutation window needs to be accounted for.
    - Full-table bootstrap (no watermark) loads the full ML output history.
    """

    source_name: str = SOURCE_NAME
    schema_row_class: type[WarehouseRow] = TopicsRow
    inclusion_mode: str = INCLUSION_MODE
    freshness_field: str | None = FRESHNESS_FIELD     # processed_at
    primary_key_fields: tuple[str, ...] = PRIMARY_KEYS
    default_chunk_size: int = 5000
    supports_incremental: bool = True

    # ── Source column contract ────────────────────────────────────────────────

    def get_source_columns(self) -> tuple[str, ...]:
        """
        Return the explicit ordered source columns for fct_topics.

        These columns must stay aligned with TopicsRow.from_row().
        Adding or removing a column here requires a matching change in
        the schema row dataclass.

        Composite content-entity identity note:
            source_type, item_id, and user_id together identify the
            classified entity. All three must be present for downstream
            Topic node and DISCUSSED edge construction.

        Provenance note:
            model_provider and model_version are ML lineage fields.
            Required for downstream model drift detection and reprocessing
            decisions; must not be dropped.
        """
        return (
            "id",
            "source_type",
            "item_id",
            "user_id",
            "topic_label",
            "reasoning",
            "processed_at",
            "model_provider",
            "model_version",
        )

    # ── Query construction ────────────────────────────────────────────────────

    def build_base_query(self) -> str:
        """
        Return the base SELECT for fct_topics without incremental filtering.

        The incremental clause (WHERE processed_at > %(watermark_value)s)
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
        Build the incremental filter using processed_at.

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
        Return stable deterministic ordering for fct_topics.

        processed_at first — aligns with watermark advancement and clusters
        output by ML processing batch, which is the natural downstream
        consumption pattern for topic signal ingestion.

        id second — integer surrogate PK; breaks ties within the same
        processed_at timestamp bucket deterministically.
        """
        return "\nORDER BY processed_at, id"

    def build_pagination_clause(self, limit: int, offset: int) -> str:
        """
        Return LIMIT/OFFSET pagination clause.
        """
        return "\nLIMIT %(limit)s OFFSET %(offset)s"