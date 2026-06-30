"""
Extractor for the fct_financials warehouse source.

Purpose:
- Extract payment and financial event rows from fct_financials, including
  event identity, amount, currency, timing, MRR delta, payment method,
  and user/subscription references.
- Incremental strategy using event_at_utc as the watermark.
- Return typed FinancialsRow instances wrapped in ExtractorBatch.

Source characteristics:
    fct_financials is an append-oriented financial event log — one row per
    payment or financial event. Rows are written once and not updated after
    initial insert; event_at_utc is the authoritative event timestamp.
    Incremental extraction is therefore complete and correct with no
    mutation window required.

    subscription_type_id is an integer FK to dim_subscription_products.
    It links each financial event to the subscription tier that generated
    the revenue, which is required for MRR attribution in downstream
    financial analytics.

    transaction_id is a payment processor transaction reference (e.g.
    Stripe charge ID). It is extracted faithfully for operational
    reconciliation but must not propagate into graph node properties
    or public API responses — it is an internal payment system reference.

Financial precision:
    amount and mrr_change are DECIMAL(10,2) in the DWH; stored as
    float | None. Downstream financial aggregations should use
    precision-safe arithmetic (Python Decimal or equivalent) to avoid
    cumulative rounding errors, particularly for MRR calculations where
    small deltas accumulate across many events.

Design rules:
- event_id is VARCHAR(100); preserved as str.
- amount and mrr_change are DECIMAL stored as float; precision-safe
  arithmetic required downstream for financial aggregations.
- transaction_id is an operational payment reference; extracted faithfully
  but treated as internal-only.
- subscription_type_id is an integer FK preserved for revenue attribution.
- No graph logic, canonicalization, or enrichment is applied here.

Source schema:
- Source table  : fct_financials
- Inclusion mode: GRAPH_CORE
- Graph entity  : FinancialEvent
- Freshness field: event_at_utc
"""

from __future__ import annotations

from app.contracts.warehouse_rows import WarehouseRow
from app.extractors.base import BaseExtractor
from app.schemas.warehouse.financials import (
    FRESHNESS_FIELD,
    INCLUSION_MODE,
    PRIMARY_KEYS,
    SOURCE_NAME,
    FinancialsRow,
)


class FinancialsExtractor(BaseExtractor):
    """
    Extractor for fct_financials.

    Incremental strategy:
    - watermark field: event_at_utc
    - ordering: event_at_utc, event_id

    Append-oriented semantics:
    - Financial events are written once and not updated. Incremental
      extraction is therefore complete and correct.

    Financial precision:
    - amount and mrr_change are DECIMAL(10,2) stored as float | None.
      Downstream MRR aggregations must use precision-safe arithmetic.

    Payment reference:
    - transaction_id is an internal payment processor reference.
      Extracted faithfully; must not propagate to graph properties or
      public API responses.
    """

    source_name: str = SOURCE_NAME
    schema_row_class: type[WarehouseRow] = FinancialsRow
    inclusion_mode: str = INCLUSION_MODE
    freshness_field: str | None = FRESHNESS_FIELD     # event_at_utc
    primary_key_fields: tuple[str, ...] = PRIMARY_KEYS
    default_chunk_size: int = 5000
    supports_incremental: bool = True

    # ── Source column contract ────────────────────────────────────────────────

    def get_source_columns(self) -> tuple[str, ...]:
        """
        Return the explicit ordered source columns for fct_financials.

        These columns must stay aligned with FinancialsRow.from_row().
        Adding or removing a column here requires a matching change in
        the schema row dataclass.

        DECIMAL fields note:
            amount, mrr_change — DECIMAL(10,2); stored as float | None.
            Downstream MRR and revenue aggregations must use precision-safe
            arithmetic to avoid cumulative rounding errors.

        Payment reference note:
            transaction_id — internal payment processor reference (e.g.
            Stripe charge ID). Extracted for operational reconciliation;
            must not reach graph node properties or public API responses.

        FK note:
            subscription_type_id — integer FK to dim_subscription_products;
            required for revenue attribution to subscription tier.
        """
        return (
            "event_id",
            "amount",                  # DECIMAL(10,2) — float | None
            "currency",
            "event_at_utc",
            "event_date_key",          # INTEGER partition label; str | None
            "event_type",
            "mrr_change",              # DECIMAL(10,2) — float | None
            "payment_method",
            "payment_status",
            "subscription_type_id",    # FK to dim_subscription_products
            "transaction_id",          # payment processor ref — operational only
            "user_id",
        )

    # ── Query construction ────────────────────────────────────────────────────

    def build_base_query(self) -> str:
        """
        Return the base SELECT for fct_financials without incremental filtering.

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
        Return stable deterministic ordering for fct_financials.

        event_at_utc first — aligns with watermark advancement and clusters
        output by financial event time, matching the natural downstream
        consumption pattern for revenue and MRR processing.

        event_id second — VARCHAR PK; breaks ties within the same event
        timestamp bucket deterministically.
        """
        return "\nORDER BY event_at_utc, event_id"

    def build_pagination_clause(self, limit: int, offset: int) -> str:
        """
        Return LIMIT/OFFSET pagination clause.
        """
        return "\nLIMIT %(limit)s OFFSET %(offset)s"