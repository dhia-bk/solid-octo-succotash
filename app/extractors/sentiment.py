"""
Extractor for the fct_sentiment warehouse source.

Purpose:
- Extract ML-derived sentiment rows from fct_sentiment, including source_type,
  item_id, user_id, sentiment label, score fields, processing metadata, and
  pipeline_run_id.
- Incremental strategy using processed_at as the watermark.
- Return typed SentimentRow instances wrapped in ExtractorBatch.

No single-column primary key:
    fct_sentiment has no declared single-column PK in the DWH. The stable row
    identifier is the composite key (source_type, item_id, user_id). All three
    fields are nullable at the column level but must be treated as required
    together for a valid, identifiable sentiment row.

    The extractor must preserve all three composite identity fields so the
    transformer can invoke stable_hash_key(source_type, item_id, user_id) to
    produce the synthetic graph node ID for Sentiment node merges and
    EXPRESSED edge construction.

Ordering tiebreak rationale:
    Because there is no integer surrogate PK, the tiebreak after processed_at
    must use the composite key fields (source_type, item_id, user_id). This
    produces a fully deterministic ordering across all rows within the same
    processed_at timestamp bucket without relying on any implicit row ordering
    from the database engine.

Design rules:
- source_type, item_id, and user_id are the synthetic key inputs. All three
  must be preserved exactly and must never be dropped or coerced in SQL.
- pipeline_run_id is an ML provenance field linking this row to the specific
  model pipeline execution that produced it. Required for lineage tracking;
  must not be dropped.
- text_hash is a content deduplication signal used by the ML pipeline to
  avoid reprocessing identical content. Preserved faithfully at extraction.
- All score_* fields are FLOAT in the DWH; SentimentRow stores them as
  float | None.
- No graph logic, canonicalization, or synthetic key generation is applied
  here. Synthetic key generation belongs to the transformer layer.

Source schema:
- Source table  : fct_sentiment
- Inclusion mode: GRAPH_CORE
- Graph entity  : Sentiment
- Freshness field: processed_at
- Declared PK   : None (composite: source_type, item_id, user_id)
"""

from __future__ import annotations

from app.contracts.warehouse_rows import WarehouseRow
from app.extractors.base import BaseExtractor
from app.schemas.warehouse.sentiment import (
    FRESHNESS_FIELD,
    INCLUSION_MODE,
    PRIMARY_KEYS,
    SOURCE_NAME,
    SentimentRow,
)


class SentimentExtractor(BaseExtractor):
    """
    Extractor for fct_sentiment.

    Incremental strategy:
    - watermark field: processed_at
    - ordering: processed_at, source_type, item_id, user_id

    No surrogate PK:
    - primary_key_fields is set to the composite key tuple declared in the
      schema module: ("source_type", "item_id", "user_id"). The base runtime
      uses this for ordering fallback and validation; the composite tiebreak
      in build_order_by_clause() overrides the default ordering logic.
    - All three composite key fields are nullable in the DWH. Rows where any
      of the three is NULL will sort with NULLs last (standard SQL behaviour),
      which is acceptable — such rows are anomalous and will be filtered or
      flagged by the transformer's identity validation step.

    Append-oriented semantics:
    - Like fct_topics, sentiment rows are written once by the ML pipeline and
      are not updated after initial processing. Incremental extraction by
      processed_at is therefore complete and correct with no mutation window
      required.
    """

    source_name: str = SOURCE_NAME
    schema_row_class: type[WarehouseRow] = SentimentRow
    inclusion_mode: str = INCLUSION_MODE
    freshness_field: str | None = FRESHNESS_FIELD     # processed_at
    primary_key_fields: tuple[str, ...] = PRIMARY_KEYS  # composite; no surrogate
    default_chunk_size: int = 5000
    supports_incremental: bool = True

    # ── Source column contract ────────────────────────────────────────────────

    def get_source_columns(self) -> tuple[str, ...]:
        """
        Return the explicit ordered source columns for fct_sentiment.

        These columns must stay aligned with SentimentRow.from_row().
        Adding or removing a column here requires a matching change in
        the schema row dataclass.

        Synthetic key identity note:
            source_type, item_id, and user_id are the inputs to
            stable_hash_key() in the transformer layer. All three must be
            present in every extracted row. Do not drop or filter on these
            fields at the extractor layer.

        Provenance fields:
            model_provider, model_version — ML lineage; required for drift
                detection and reprocessing decisions.
            pipeline_run_id — links each row to the specific ML pipeline run
                that produced it; required for lineage tracking.
            text_hash — content deduplication signal used by the ML pipeline;
                preserved faithfully for downstream deduplication checks.
        """
        return (
            "source_type",       # synthetic key input — must not be dropped
            "item_id",           # synthetic key input — must not be dropped
            "user_id",           # synthetic key input — must not be dropped
            "created_at",
            "processed_at",
            "language_code",
            "sentiment_label",
            "score_positive",
            "score_negative",
            "score_neutral",
            "score_mixed",
            "model_provider",
            "model_version",
            "pipeline_run_id",   # ML provenance — must not be dropped
            "text_hash",
        )

    # ── Query construction ────────────────────────────────────────────────────

    def build_base_query(self) -> str:
        """
        Return the base SELECT for fct_sentiment without incremental filtering.

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
        Return stable deterministic ordering for fct_sentiment.

        processed_at first — aligns with watermark advancement and clusters
        output by ML processing batch.

        source_type, item_id, user_id as tiebreakers — the composite key
        fields that form the stable row identity in the absence of a
        surrogate PK. This ordering is fully deterministic across any two
        runs on the same dataset. NULL values in any tiebreak field will
        sort last under standard SQL semantics.
        """
        return "\nORDER BY processed_at, source_type, item_id, user_id"

    def build_pagination_clause(self, limit: int, offset: int) -> str:
        """
        Return LIMIT/OFFSET pagination clause.
        """
        return "\nLIMIT %(limit)s OFFSET %(offset)s"