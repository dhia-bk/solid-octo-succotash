"""
Extractor for the fct_prediction_duels warehouse source.

Purpose:
- Extract head-to-head prediction duel rows from fct_prediction_duels,
  including fixture, sender/receiver, linked predictions, entry fee,
  status, winner, and timestamps.
- Incremental strategy using created_at_utc as the watermark.
- Return typed PredictionDuelsRow instances wrapped in ExtractorBatch.

Source characteristics:
    fct_prediction_duels records head-to-head prediction challenges between
    two users with coin stakes. Each duel is created when the sender issues
    a challenge; it then transitions through status states (pending →
    accepted/declined → processed) as the receiver responds and the fixture
    result is applied.

    Filtering by created_at_utc captures new duels correctly on incremental
    runs but will miss status, winner_user_id, is_processed, and
    processed_at_utc updates on existing duels. These fields mutate after
    creation as the duel lifecycle progresses.

    For most pipeline use cases this is acceptable — duel identity and coin
    stake are immutable after creation; lifecycle state updates are
    low-frequency and typically complete within the fixture result window.
    Pipeline operators who need accurate lifecycle state on historical duels
    should schedule periodic full-refresh runs or use a bounded active-window
    approach similar to the fixtures extractor.

Design rules:
- duel_id and fixture_id are VARCHAR in the DWH; preserved as str / str | None.
- sender_user_id, receiver_user_id, and winner_user_id are string FKs to
  dim_users; all three must be preserved for CHALLENGED edge construction
  and duel outcome attribution.
- sender_prediction_id and receiver_prediction_id are FKs to fct_predictions;
  preserved as str | None for downstream prediction-duel linkage.
- is_processed is a TINYINT 0/1 lifecycle flag; stored as int | None.
- No graph logic, canonicalization, or enrichment is applied here.

Source schema:
- Source table  : fct_prediction_duels
- Inclusion mode: GRAPH_CORE
- Graph entity  : Duel
- Freshness field: created_at_utc
"""

from __future__ import annotations

from app.contracts.warehouse_rows import WarehouseRow
from app.extractors.base import BaseExtractor
from app.schemas.warehouse.prediction_duels import (
    FRESHNESS_FIELD,
    INCLUSION_MODE,
    PRIMARY_KEYS,
    SOURCE_NAME,
    PredictionDuelsRow,
)


class PredictionDuelsExtractor(BaseExtractor):
    """
    Extractor for fct_prediction_duels.

    Incremental strategy:
    - watermark field: created_at_utc
    - ordering: created_at_utc, duel_id

    Lifecycle state limitation:
    - status, winner_user_id, is_processed, and processed_at_utc all mutate
      after duel creation. Incremental runs by created_at_utc capture new
      duels only; lifecycle state updates on existing duels are not
      re-extracted. Schedule periodic full-refresh runs when accurate
      duel outcome state on historical duels is required.
    """

    source_name: str = SOURCE_NAME
    schema_row_class: type[WarehouseRow] = PredictionDuelsRow
    inclusion_mode: str = INCLUSION_MODE
    freshness_field: str | None = FRESHNESS_FIELD     # created_at_utc
    primary_key_fields: tuple[str, ...] = PRIMARY_KEYS
    default_chunk_size: int = 5000
    supports_incremental: bool = True

    # ── Source column contract ────────────────────────────────────────────────

    def get_source_columns(self) -> tuple[str, ...]:
        """
        Return the explicit ordered source columns for fct_prediction_duels.

        These columns must stay aligned with PredictionDuelsRow.from_row().
        Adding or removing a column here requires a matching change in
        the schema row dataclass.

        Lifecycle state note:
            status, winner_user_id, is_processed, and processed_at_utc are
            mutable after duel creation. All four must be preserved so the
            transformer has the most recently extracted lifecycle state
            available, even if it may lag on historical duels.

        Participant FK note:
            sender_user_id, receiver_user_id, and winner_user_id are all
            string FKs to dim_users. All three must be preserved; the
            transformer constructs CHALLENGED edges and outcome attribution
            from this set.
        """
        return (
            "duel_id",
            "fixture_id",
            "sender_user_id",
            "receiver_user_id",
            "sender_prediction_id",
            "receiver_prediction_id",
            "entry_fee",
            "status",                 # mutable — see lifecycle state note
            "winner_user_id",         # mutable — populated after fixture result
            "is_processed",           # mutable — TINYINT lifecycle flag
            "created_at_utc",
            "processed_at_utc",       # mutable — NULL until duel is settled
        )

    # ── Query construction ────────────────────────────────────────────────────

    def build_base_query(self) -> str:
        """
        Return the base SELECT for fct_prediction_duels without incremental
        filtering.

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
        Return stable deterministic ordering for fct_prediction_duels.

        created_at_utc first — aligns with watermark advancement and clusters
        output by duel creation time.

        duel_id second — VARCHAR PK; breaks ties within the same creation
        timestamp bucket deterministically.
        """
        return "\nORDER BY created_at_utc, duel_id"

    def build_pagination_clause(self, limit: int, offset: int) -> str:
        """
        Return LIMIT/OFFSET pagination clause.
        """
        return "\nLIMIT %(limit)s OFFSET %(offset)s"