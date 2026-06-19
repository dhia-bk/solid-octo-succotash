"""
Extractor for the fct_voucher_purchases warehouse source.

Purpose:
- Extract voucher purchase events from fct_voucher_purchases, including
  user, voucher_id, voucher_key, coin cost, lifecycle timestamps, redemption
  status, and acquisition context.
- Incremental strategy using purchase_date_utc as the watermark.
- Return typed VoucherPurchasesRow instances wrapped in ExtractorBatch.

Source characteristics:
    fct_voucher_purchases records each voucher purchase as a distinct row.
    Rows are created at purchase time; is_used, used_date_utc, used_date_key,
    days_to_redemption, and voucher_status can update after the initial
    purchase when the voucher is redeemed. Filtering by purchase_date_utc
    captures new purchases correctly but will miss redemption state updates
    on existing purchase rows.

    For most pipeline use cases this is acceptable — purchase identity and
    coin cost are immutable after the initial purchase event; redemption state
    is a distinct lifecycle signal that pipeline operators can capture via a
    periodic full-refresh if needed.

Dual voucher reference fields:
    Each row carries both voucher_id (a surrogate VARCHAR key from the
    originating system) and voucher_key (the stable catalog key from
    dim_voucher_catalog). Both must be preserved — voucher_id is used for
    operational FK resolution; voucher_key is the canonical graph join key
    for PURCHASED edge construction.

Sensitive fields:
    voucher_code is the redemption code for the specific purchased voucher
    instance. Extracted faithfully from source truth; must not propagate
    into graph DTOs or API responses unchanged.
    ad_reward_token and ad_unit_id are advertising attribution fields;
    extracted faithfully but treated as operational-only.

No declared primary key:
    purchase_id has no PK constraint in the DWH. It is the stable de facto
    key at extraction time; deduplication is a transformer concern.

Design rules:
- purchase_id is the stable de facto key; preserved exactly as sourced.
- voucher_id and voucher_key are both FK references to the voucher catalog;
  both must be preserved for transformer-layer edge routing.
- All *_date_key fields are INTEGER partition labels; stored as str | None.
- No graph logic, canonicalization, or enrichment is applied here.

Source schema:
- Source table  : fct_voucher_purchases
- Inclusion mode: GRAPH_CORE
- Graph entity  : PURCHASED relationship (User → Voucher)
- Freshness field: purchase_date_utc
- Declared PK   : None (purchase_id treated as stable de facto key)
"""

from __future__ import annotations

from app.contracts.warehouse_rows import WarehouseRow
from app.extractors.base import BaseExtractor
from app.schemas.warehouse.voucher_purchases import (
    FRESHNESS_FIELD,
    INCLUSION_MODE,
    PRIMARY_KEYS,
    SOURCE_NAME,
    VoucherPurchasesRow,
)


class VoucherPurchasesExtractor(BaseExtractor):
    """
    Extractor for fct_voucher_purchases.

    Incremental strategy:
    - watermark field: purchase_date_utc
    - ordering: purchase_date_utc, purchase_id

    Redemption state limitation:
    - is_used, used_date_utc, used_date_key, days_to_redemption, and
      voucher_status can update after purchase. Incremental runs capture
      new purchases only; redemption updates on existing rows are not
      re-extracted. Schedule periodic full-refresh runs when accurate
      redemption state on historical purchases is required.

    Dual voucher reference:
    - voucher_id (surrogate system key) and voucher_key (catalog key) are
      both preserved for FK routing and PURCHASED edge construction.
    """

    source_name: str = SOURCE_NAME
    schema_row_class: type[WarehouseRow] = VoucherPurchasesRow
    inclusion_mode: str = INCLUSION_MODE
    freshness_field: str | None = FRESHNESS_FIELD     # purchase_date_utc
    primary_key_fields: tuple[str, ...] = PRIMARY_KEYS
    default_chunk_size: int = 5000
    supports_incremental: bool = True

    # ── Source column contract ────────────────────────────────────────────────

    def get_source_columns(self) -> tuple[str, ...]:
        """
        Return the explicit ordered source columns for fct_voucher_purchases.

        These columns must stay aligned with VoucherPurchasesRow.from_row().
        Adding or removing a column here requires a matching change in
        the schema row dataclass.

        Dual voucher reference note:
            voucher_id — surrogate FK from originating system.
            voucher_key — canonical catalog key from dim_voucher_catalog.
            Both must be preserved; the transformer uses voucher_key for
            PURCHASED edge construction and voucher_id for operational FK
            resolution.

        Sensitive fields note:
            voucher_code — per-purchase redemption code; must not reach
                graph/API boundary.
            ad_reward_token, ad_unit_id — advertising attribution; treated
                as operational-only.

        Redemption state fields note:
            is_used, used_date_utc, used_date_key, days_to_redemption,
            voucher_status — mutable after purchase; see class docstring
            for incremental limitation.
        """
        return (
            "purchase_id",
            "user_id",
            "voucher_id",             # surrogate system FK
            "voucher_code",           # sensitive — must not reach graph/API boundary
            "coin_cost",
            "purchase_date_utc",
            "purchase_date_key",      # INTEGER partition label; str | None
            "expiry_date_utc",
            "expiry_date_key",        # INTEGER partition label; str | None
            "is_used",                # mutable — updated on redemption
            "used_date_utc",          # mutable — NULL until redeemed
            "used_date_key",          # mutable — INTEGER partition label; str | None
            "acquisition_type",
            "ad_reward_token",        # advertising attribution — operational only
            "ad_unit_id",             # advertising attribution — operational only
            "days_to_redemption",     # mutable — computed from used_date_utc
            "voucher_status",         # mutable — lifecycle state
            "voucher_key",            # canonical catalog key from dim_voucher_catalog
        )

    # ── Query construction ────────────────────────────────────────────────────

    def build_base_query(self) -> str:
        """
        Return the base SELECT for fct_voucher_purchases without incremental
        filtering.

        The incremental clause (WHERE purchase_date_utc > %(watermark_value)s)
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
        Build the incremental filter using purchase_date_utc.

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
        Return stable deterministic ordering for fct_voucher_purchases.

        purchase_date_utc first — aligns with watermark advancement and
        clusters output by purchase time, matching the natural downstream
        consumption pattern for economy event processing.

        purchase_id second — de facto PK; breaks ties within the same
        purchase timestamp bucket deterministically.
        """
        return "\nORDER BY purchase_date_utc, purchase_id"

    def build_pagination_clause(self, limit: int, offset: int) -> str:
        """
        Return LIMIT/OFFSET pagination clause.
        """
        return "\nLIMIT %(limit)s OFFSET %(offset)s"