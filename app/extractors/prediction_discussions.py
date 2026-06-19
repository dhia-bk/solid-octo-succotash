"""
Extractor for the dim_prediction_discussions warehouse source.

Purpose:
- Extract prediction-specific discussion thread identity from
  dim_prediction_discussions, including prediction_discussion_id,
  creation time, discussion type, and prediction_id.
- Incremental strategy using created_at_utc as the watermark.
- Return typed PredictionDiscussionsRow instances wrapped in ExtractorBatch.

Source characteristics:
    dim_prediction_discussions is a low-churn identity table, distinct from
    dim_discussions which holds fixture-level threads. Each row represents
    a discussion thread anchored to a specific prediction rather than a
    fixture. These threads are created once at prediction time and are not
    substantially mutated thereafter.

    prediction_id is INTEGER in the DWH but is normalized to str | None in
    PredictionDiscussionsRow for cross-entity consistency with fct_predictions
    where prediction_id is stored as VARCHAR. No SQL-level CAST is required;
    from_row() handles the Python-level coercion.

    fct_discussion_events references prediction_discussion_id as a FK
    (alongside discussion_id for fixture threads). Rows extracted here are
    the parent node records for those events.

Design rules:
- prediction_discussion_id is an INTEGER PK; stored as int in the typed row.
- prediction_id type normalization (INTEGER → str) is applied in from_row(),
  not in SQL, to remain consistent with the project-wide ID normalization
  pattern.
- discussion_type distinguishes thread variants (e.g. public vs private
  prediction discussions); preserved exactly for downstream routing.
- No graph logic, canonicalization, or enrichment is applied here.

Source schema:
- Source table  : dim_prediction_discussions
- Inclusion mode: GRAPH_CORE
- Graph entity  : PredictionDiscussion
- Freshness field: created_at_utc
"""

from __future__ import annotations

from app.contracts.warehouse_rows import WarehouseRow
from app.extractors.base import BaseExtractor
from app.schemas.warehouse.prediction_discussions import (
    FRESHNESS_FIELD,
    INCLUSION_MODE,
    PRIMARY_KEYS,
    SOURCE_NAME,
    PredictionDiscussionsRow,
)


class PredictionDiscussionsExtractor(BaseExtractor):
    """
    Extractor for dim_prediction_discussions.

    Incremental strategy:
    - watermark field: created_at_utc
    - ordering: created_at_utc, prediction_discussion_id

    Relationship to discussion events:
    - fct_discussion_events references prediction_discussion_id as a FK
      for prediction-thread events. Rows here are the parent identity
      records for those events; both must be extracted for the transformer
      to construct JOINED_DISCUSSION edges on prediction threads.
    """

    source_name: str = SOURCE_NAME
    schema_row_class: type[WarehouseRow] = PredictionDiscussionsRow
    inclusion_mode: str = INCLUSION_MODE
    freshness_field: str | None = FRESHNESS_FIELD     # created_at_utc
    primary_key_fields: tuple[str, ...] = PRIMARY_KEYS
    default_chunk_size: int = 2000                    
    supports_incremental: bool = True

    # ── Source column contract ────────────────────────────────────────────────

    def get_source_columns(self) -> tuple[str, ...]:
        """
        Return the explicit ordered source columns for dim_prediction_discussions.

        These columns must stay aligned with PredictionDiscussionsRow.from_row().
        Adding or removing a column here requires a matching change in
        the schema row dataclass.

        prediction_id type note:
            INTEGER in the DWH; from_row() casts to str | None for
            cross-entity consistency with fct_predictions (VARCHAR). No
            SQL-level CAST is applied here.
        """
        return (
            "prediction_discussion_id",
            "created_at_utc",
            "discussion_type",
            "prediction_id",    # INTEGER in DWH; coerced to str in from_row()
        )

    # ── Query construction ────────────────────────────────────────────────────

    def build_base_query(self) -> str:
        """
        Return the base SELECT for dim_prediction_discussions without
        incremental filtering.

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
        Return stable deterministic ordering for dim_prediction_discussions.

        created_at_utc first — aligns with watermark advancement and clusters
        output by thread creation time.

        prediction_discussion_id second — integer PK; breaks ties within the
        same creation timestamp bucket deterministically. Integer sort order
        is naturally correct without CAST.
        """
        return "\nORDER BY created_at_utc, prediction_discussion_id"

    def build_pagination_clause(self, limit: int, offset: int) -> str:
        """
        Return LIMIT/OFFSET pagination clause.
        """
        return "\nLIMIT %(limit)s OFFSET %(offset)s"