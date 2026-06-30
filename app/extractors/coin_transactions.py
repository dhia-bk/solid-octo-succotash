"""
Extractor for the fct_coin_transactions warehouse source.

Purpose:
- Extract coin economy earn/spend events from fct_coin_transactions,
  including transaction/event identity, user, amount, balance-after,
  description, and event time.
- Incremental strategy using event_at_utc as the watermark.
- Return typed CoinTransactionsRow instances wrapped in ExtractorBatch.

Source characteristics:
    fct_coin_transactions is an append-oriented financial event log — one
    row per coin earn or spend event. Rows are written once and are not
    updated after initial insert; event_at_utc is the authoritative event
    timestamp. Incremental extraction is therefore complete and correct with
    no mutation window required.

    coin_amount and coin_balance_after are DECIMAL(18,4) in the DWH; stored
    as float | None in the typed row. Downstream financial aggregation should
    use Python's Decimal type or equivalent precision-safe arithmetic, not
    raw float operations, to avoid cumulative rounding errors.

    primary_id and secondary_id are generic polymorphic reference fields
    whose meaning depends on event_type (e.g. for a prediction reward event,
    primary_id may reference a prediction_id; for a purchase, it may reference
    a voucher_id). Both are preserved exactly as sourced; semantic resolution
    belongs to the transformer layer.

Design rules:
- event_id is VARCHAR(100); preserved as str.
- user_id is a string FK to dim_users; preserved as-is.
- coin_amount and coin_balance_after are DECIMAL in the DWH; stored as
  float | None. No SQL CAST applied — the DWH driver handles DECIMAL-to-float
  conversion at the cursor level.
- primary_id and secondary_id are polymorphic references; preserved without
  semantic interpretation.
- No graph logic, canonicalization, or enrichment is applied here.

Source schema:
- Source table  : fct_coin_transactions
- Inclusion mode: GRAPH_CORE
- Graph entity  : CoinTransaction
- Freshness field: event_at_utc
"""

from __future__ import annotations

from app.contracts.warehouse_rows import WarehouseRow
from app.extractors.base import BaseExtractor
from app.schemas.warehouse.coin_transactions import (
    FRESHNESS_FIELD,
    INCLUSION_MODE,
    PRIMARY_KEYS,
    SOURCE_NAME,
    CoinTransactionsRow,
)


class CoinTransactionsExtractor(BaseExtractor):
    """
    Extractor for fct_coin_transactions.

    Incremental strategy:
    - watermark field: event_at_utc
    - ordering: event_at_utc, event_id

    Append-oriented semantics:
    - Coin events are written once and not updated. Incremental extraction
      is therefore complete and correct with no mutation window required.

    Decimal precision note:
    - coin_amount and coin_balance_after are DECIMAL(18,4) in the DWH,
      stored as float | None here. Downstream aggregations should use
      precision-safe arithmetic to avoid cumulative rounding errors.

    Polymorphic reference fields:
    - primary_id and secondary_id carry event-type-dependent semantics.
      Both are preserved as strings without interpretation; semantic
      resolution belongs to the transformer layer.
    """

    source_name: str = SOURCE_NAME
    schema_row_class: type[WarehouseRow] = CoinTransactionsRow
    inclusion_mode: str = INCLUSION_MODE
    freshness_field: str | None = FRESHNESS_FIELD     # event_at_utc
    primary_key_fields: tuple[str, ...] = PRIMARY_KEYS
    default_chunk_size: int = 5000                    
    supports_incremental: bool = True

    # ── Source column contract ────────────────────────────────────────────────

    def get_source_columns(self) -> tuple[str, ...]:
        """
        Return the explicit ordered source columns for fct_coin_transactions.

        These columns must stay aligned with CoinTransactionsRow.from_row().
        Adding or removing a column here requires a matching change in
        the schema row dataclass.

        Decimal fields note:
            coin_amount, coin_balance_after — DECIMAL(18,4) in the DWH;
            from_row() stores as float | None. Downstream aggregations should
            use precision-safe arithmetic.

        Polymorphic reference note:
            primary_id, secondary_id — event-type-dependent references.
            Preserved without semantic interpretation; meaning resolved by
            the transformer using event_type as the discriminator.

        Partition label note:
            event_date_key is an INTEGER in the DWH but is a partition label;
            stored as str | None.
        """
        return (
            "event_id",
            "user_id",
            "transaction_type",
            "event_type",
            "primary_id",           # polymorphic reference — event_type discriminates
            "secondary_id",         # polymorphic reference — event_type discriminates
            "coin_amount",          # DECIMAL(18,4) — stored as float | None
            "coin_balance_after",   # DECIMAL(18,4) — stored as float | None
            "description",
            "event_at_utc",
            "event_date_key",       # INTEGER partition label; str | None
        )

    # ── Query construction ────────────────────────────────────────────────────

    def build_base_query(self) -> str:
        """
        Return the base SELECT for fct_coin_transactions without incremental
        filtering.

        The incremental clause (WHERE event_at_utc > :watermark_value)
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
        Build the incremental filter using event_at_utc.

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
        Return stable deterministic ordering for fct_coin_transactions.

        event_at_utc first — aligns with watermark advancement and clusters
        output by transaction time, matching the natural downstream consumption
        pattern for financial event processing.

        event_id second — VARCHAR PK; breaks ties within the same event
        timestamp bucket deterministically.
        """
        return "\nORDER BY event_at_utc, event_id"

    def build_pagination_clause(self, limit: int, offset: int) -> str:
        """
        Return LIMIT/OFFSET pagination clause.
        """
        return "\nLIMIT %(limit)s OFFSET %(offset)s"