"""
Extractor for the fct_subscription_lifecycle warehouse source.

Purpose:
- Extract subscription lifecycle events from fct_subscription_lifecycle,
  including event type, timestamps, product IDs, billing/revenue metrics,
  churn/win-back signals, and payment metadata.
- Incremental strategy using event_timestamp_utc as the watermark.
- Return typed SubscriptionLifecycleRow instances wrapped in ExtractorBatch.

Source characteristics:
    fct_subscription_lifecycle is an append-oriented event log — one row per
    lifecycle event (new subscription, renewal, churn, win-back). Rows are
    written once and not updated after initial insert. Incremental extraction
    by event_timestamp_utc is therefore complete and correct.

    subscription_product_id and previous_product_id are integer FKs to
    dim_subscription_products. Both must be preserved for SUBSCRIBED_TO edge
    construction and tier-change analysis.

DATE column handling:
    subscription_start_date and subscription_end_date are DATE columns in the
    DWH, stored as str | None in SubscriptionLifecycleRow. These are date-only
    values and must not be converted to datetime to avoid spurious timezone
    shifts on date-only values.

Payment metadata sensitivity:
    payment_intent_id is a payment processor reference (e.g. Stripe
    PaymentIntent ID). It is extracted faithfully from source truth for
    operational reconciliation but must not propagate into graph node
    properties or public API responses. It is an internal payment system
    reference, not a user-facing identifier.

Design rules:
- lifecycle_event_id has no PK constraint; treated as the stable de facto key.
- All DECIMAL fields (amount_paid_usd, lifetime_subscription_revenue_usd,
  churn_risk_score, mrr_renewal_delta, mrr_new_delta) are stored as float | None.
  Downstream financial aggregations should use precision-safe arithmetic.
- subscription_start_date and subscription_end_date are DATE str | None;
  do not apply warehouse_value_to_utc_datetime to these fields.
- No graph logic, canonicalization, or enrichment is applied here.

Source schema:
- Source table  : fct_subscription_lifecycle
- Inclusion mode: GRAPH_CORE
- Graph entity  : SUBSCRIBED_TO relationship (User → SubscriptionProduct)
- Freshness field: event_timestamp_utc
- Declared PK   : None (lifecycle_event_id treated as stable de facto key)
"""

from __future__ import annotations

from app.contracts.warehouse_rows import WarehouseRow
from app.extractors.base import BaseExtractor
from app.schemas.warehouse.subscription_lifecycle import (
    FRESHNESS_FIELD,
    INCLUSION_MODE,
    PRIMARY_KEYS,
    SOURCE_NAME,
    SubscriptionLifecycleRow,
)


class SubscriptionLifecycleExtractor(BaseExtractor):
    """
    Extractor for fct_subscription_lifecycle.

    Incremental strategy:
    - watermark field: event_timestamp_utc
    - ordering: event_timestamp_utc, lifecycle_event_id

    Append-oriented semantics:
    - Lifecycle events are written once and not updated. Incremental
      extraction is therefore complete and correct with no mutation window.

    Payment metadata:
    - payment_intent_id is an internal payment processor reference.
      Extracted faithfully; must not propagate to graph node properties
      or public API responses.

    No declared PK:
    - lifecycle_event_id is treated as the stable de facto key.
      Deduplication is a transformer concern.
    """

    source_name: str = SOURCE_NAME
    schema_row_class: type[WarehouseRow] = SubscriptionLifecycleRow
    inclusion_mode: str = INCLUSION_MODE
    freshness_field: str | None = FRESHNESS_FIELD     # event_timestamp_utc
    primary_key_fields: tuple[str, ...] = PRIMARY_KEYS
    default_chunk_size: int = 5000
    supports_incremental: bool = True

    # ── Source column contract ────────────────────────────────────────────────

    def get_source_columns(self) -> tuple[str, ...]:
        """
        Return the explicit ordered source columns for fct_subscription_lifecycle.

        These columns must stay aligned with SubscriptionLifecycleRow.from_row().
        Adding or removing a column here requires a matching change in
        the schema row dataclass.

        DATE column note:
            subscription_start_date, subscription_end_date — DATE columns;
            from_row() stores as str | None. Do NOT apply
            warehouse_value_to_utc_datetime to these fields.

        DECIMAL fields note:
            amount_paid_usd, lifetime_subscription_revenue_usd,
            churn_risk_score, mrr_renewal_delta, mrr_new_delta — stored as
            float | None. Downstream aggregations should use precision-safe
            arithmetic.

        Payment metadata note:
            payment_intent_id — internal payment processor reference.
            Extracted for operational reconciliation; must not reach graph
            node properties or public API responses.

        FK note:
            subscription_product_id — current tier FK to dim_subscription_products.
            previous_product_id — prior tier FK; preserved for tier-change
            analysis and SUBSCRIBED_TO edge property construction.
        """
        return (
            "lifecycle_event_id",
            "user_id",
            "subscription_product_id",              # FK to dim_subscription_products
            "event_type",
            "event_timestamp_utc",
            "event_date_key",                       # INTEGER partition label; str | None
            "subscription_start_date",              # DATE — stored as str | None
            "subscription_end_date",                # DATE — stored as str | None
            "previous_product_id",                  # prior tier FK; tier-change analysis
            "billing_cycle",
            "amount_paid_usd",                      # DECIMAL — float | None
            "payment_method",
            "cancellation_reason",
            "is_auto_renewal",
            "days_since_last_event",
            "lifetime_subscription_months",
            "lifetime_subscription_revenue_usd",    # DECIMAL — float | None
            "is_win_back",
            "churn_risk_score",                     # DECIMAL — float | None
            "currency",
            "payment_intent_id",                    # payment processor ref — operational only
            "payment_status",
            "mrr_renewal_delta",                    # DECIMAL — float | None
            "mrr_new_delta",                        # DECIMAL — float | None
        )

    # ── Query construction ────────────────────────────────────────────────────

    def build_base_query(self) -> str:
        """
        Return the base SELECT for fct_subscription_lifecycle without
        incremental filtering.

        The incremental clause
        (WHERE event_timestamp_utc > :watermark_value) is appended by
        the base runtime via build_incremental_clause().
        """
        columns = ",\n    ".join(self.get_source_columns())
        return f"""
SELECT
    {columns}
FROM {self.source_name}
""".strip()

    def build_incremental_clause(self, watermark_value: str | None) -> str:
        """
        Build the incremental filter using event_timestamp_utc.

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
        Return stable deterministic ordering for fct_subscription_lifecycle.

        event_timestamp_utc first — aligns with watermark advancement and
        clusters output by lifecycle event time, matching the natural
        downstream consumption pattern for subscription state reconstruction.

        lifecycle_event_id second — VARCHAR de facto key; breaks ties within
        the same event timestamp bucket deterministically.
        """
        return "\nORDER BY event_timestamp_utc, lifecycle_event_id"

    def build_pagination_clause(self, limit: int, offset: int) -> str:
        """
        Return LIMIT/OFFSET pagination clause.
        """
        return "\nLIMIT %(limit)s OFFSET %(offset)s"