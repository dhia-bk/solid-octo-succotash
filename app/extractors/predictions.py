"""
Extractor for the fct_predictions warehouse source.

Purpose:
- Extract user prediction facts from fct_predictions, covering public and
  private league predictions in a unified fact table.
- Incremental strategy using predicted_at_utc as the watermark.
- High-volume chunking — fct_predictions is one of the largest tables in
  the warehouse on an active platform.
- Return typed PredictionsRow instances wrapped in ExtractorBatch.

Volume and chunking:
    fct_predictions accumulates every prediction ever made on the platform.
    On active deployments this table can reach tens or hundreds of millions
    of rows. The default chunk size is set conservatively at 5 000 rows;
    pipeline operators should tune chunk_size downward if memory pressure
    is observed during large backfill runs.

    Incremental extraction by predicted_at_utc means each regular pipeline
    run touches only new predictions since the last watermark, keeping
    run times bounded regardless of total table size.

Ordering — predicted_at_utc, prediction_id:
    predicted_at_utc first — aligns watermark advancement with physical
    row order and clusters output for the most common downstream join
    pattern (predictions by time window).

    prediction_id second (not unified_prediction_id) — prediction_id is
    the natural source PK from the originating prediction system and is
    more semantically meaningful as a tiebreaker. unified_prediction_id
    is a warehouse-generated synthetic key; using it as an ordering
    tiebreaker would produce correct but arbitrarily ordered output.
    prediction_id is nullable, so NULLs will sort last (standard SQL
    behaviour) — this is acceptable because NULLs indicate rows sourced
    from a legacy prediction path that pre-dates the unified key scheme.

Design rules:
- unified_prediction_id is the warehouse PK and must always be present.
  prediction_id is nullable (legacy rows); both must be preserved.
- fixture_id, private_league_id, and influencer_league_id are VARCHAR in
  the DWH despite being conceptually numeric in some originating tables.
  Types are preserved exactly as sourced; no coercion is applied in SQL.
- *_date_key columns are INTEGER partition labels in the DWH; PredictionsRow
  stores them as str | None. No arithmetic should be applied to them.
- points_awarded is DECIMAL(10,2) in the DWH; stored as float | None.
- No graph logic, canonicalization, or enrichment is applied here.

Source schema:
- Source table  : fct_predictions
- Inclusion mode: GRAPH_CORE
- Graph entity  : PREDICTED relationship (User → Match)
- Freshness field: predicted_at_utc
"""

from __future__ import annotations

from app.contracts.warehouse_rows import WarehouseRow
from app.extractors.base import BaseExtractor
from app.schemas.warehouse.predictions import (
    FRESHNESS_FIELD,
    INCLUSION_MODE,
    PRIMARY_KEYS,
    SOURCE_NAME,
    PredictionsRow,
)


class PredictionsExtractor(BaseExtractor):
    """
    Extractor for fct_predictions.

    Incremental strategy:
    - watermark field: predicted_at_utc
    - ordering: predicted_at_utc, prediction_id

    High-volume defaults:
    - default_chunk_size: 5 000 rows per chunk
    - pipeline operators should tune downward for large backfill runs
      if memory pressure is observed

    Full-refresh bootstrap:
    - When no prior watermark exists, the base runtime omits the incremental
      clause and extracts the full table. On large platforms this may require
      a dedicated backfill pipeline run with reduced chunk_size.
    """

    source_name: str = SOURCE_NAME
    schema_row_class: type[WarehouseRow] = PredictionsRow
    inclusion_mode: str = INCLUSION_MODE
    freshness_field: str | None = FRESHNESS_FIELD     # predicted_at_utc
    primary_key_fields: tuple[str, ...] = PRIMARY_KEYS
    default_chunk_size: int = 5000                    
    supports_incremental: bool = True

    # ── Source column contract ────────────────────────────────────────────────

    def get_source_columns(self) -> tuple[str, ...]:
        """
        Return the explicit ordered source columns for fct_predictions.

        These columns must stay aligned with PredictionsRow.from_row().
        Adding or removing a column here requires a matching change in
        the schema row dataclass.

        Identity note:
            unified_prediction_id — warehouse synthetic PK; always present.
            prediction_id         — source system PK; nullable on legacy rows.
            Both must be preserved for downstream deduplication and merge-key
            construction.

        FK type notes:
            fixture_id, private_league_id, influencer_league_id — VARCHAR in
            DWH despite appearing numeric in some originating tables. Stored
            as str | None; no SQL CAST applied.
            league_id — INTEGER FK to dim_leagues.
            user_id   — string FK to dim_users.

        Partition label notes:
            prediction_date_key, kickoff_date_key, result_date_key — INTEGER
            partition keys in DWH; PredictionsRow casts to str | None.
            No numeric arithmetic should be applied to these values.
        """
        return (
            "unified_prediction_id",
            "prediction_id",
            "actual_score",
            "fixture_id",
            "influencer_league_id",
            "is_correct_result",
            "is_correct_score",
            "is_processed",
            "kickoff_at_utc",
            "league_id",
            "points_awarded",
            "predicted_at_utc",
            "predicted_outcome",
            "predicted_score",
            "prediction_context",
            "prediction_date_key",
            "private_league_id",
            "user_id",
            "winner",
            "kickoff_date_key",
            "prediction_era",
            "result_date_key",
            "source_table",
        )

    # ── Query construction ────────────────────────────────────────────────────

    def build_base_query(self) -> str:
        """
        Return the base SELECT for fct_predictions without incremental
        filtering.

        The incremental clause (WHERE predicted_at_utc > :watermark_value)
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
        Build the incremental filter using predicted_at_utc.

        Uses strict greater-than semantics so watermark advancement remains
        monotonic across runs. No clause is emitted on first run (watermark
        is None), triggering a full-table bootstrap load.
        """
        if not self.supports_incremental or not self.freshness_field:
            return ""

        if not watermark_value:
            return ""

        return f"\nWHERE {self.freshness_field} > :watermark_value"

    def build_order_by_clause(self) -> str:
        """
        Return stable deterministic ordering for fct_predictions.

        predicted_at_utc first — aligns with watermark advancement and
        clusters output for time-window-based downstream joins.

        prediction_id second — the source system PK; more semantically
        meaningful as a tiebreaker than the warehouse synthetic
        unified_prediction_id. NULL prediction_id values (legacy rows)
        sort last under standard SQL behaviour, which is acceptable.
        """
        return "\nORDER BY predicted_at_utc, prediction_id"

    def build_pagination_clause(self, limit: int, offset: int) -> str:
        """
        Return LIMIT/OFFSET pagination clause.
        """
        return "\nLIMIT %(limit)s OFFSET %(offset)s"