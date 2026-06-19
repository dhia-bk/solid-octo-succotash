"""
Extractor for the dim_voucher_catalog warehouse source.

Purpose:
- Extract voucher catalog rows from dim_voucher_catalog, including
  voucher_key, advertiser, description, terms, coin cost, expiry, stock
  levels, and redemption aggregates.
- Full-refresh strategy — although created_at is available, voucher catalog
  rows carry running aggregate columns (total_purchases, total_redeemed,
  total_coins_spent, stock_remaining, last_purchase_date) that update in-place
  as purchases occur. Filtering by created_at would correctly capture new
  vouchers but silently miss aggregate updates on existing catalog entries.
  Full refresh ensures all stock and redemption aggregates are always current.
- Return typed VoucherCatalogRow instances wrapped in ExtractorBatch.

Full-refresh rationale:
    Unlike fct_voucher_purchases (append-only event log), dim_voucher_catalog
    is a current-state dimension where aggregate columns are updated on every
    purchase. The incremental approach would require a secondary watermark
    (e.g. last_purchase_date) to capture aggregate updates, but last_purchase_date
    is itself an aggregate and may be NULL for un-purchased vouchers. Full
    refresh is the simplest and most correct strategy for a catalog of this
    type — the table is small (bounded by the number of distinct vouchers on
    offer) and full refresh cost is negligible.

No declared primary key:
    voucher_key has no PK constraint in the DWH. It is the stable de facto
    key at extraction time. The extractor preserves it exactly and must not
    attempt to deduplicate rows — that is a transformer concern.

Sensitive fields:
    voucher_code is the redemption code presented to the user at purchase.
    It is extracted faithfully from source truth but must not propagate
    into graph DTOs or API responses unchanged — downstream layers are
    responsible for enforcing this boundary.

Design rules:
- voucher_key must be preserved exactly as sourced (stable de facto key).
- advertiser_id is INTEGER in the DWH; stored as int | None in the typed row.
- All stock and aggregate columns are current-state values at extraction time.
- No graph logic, canonicalization, or enrichment is applied here.

Source schema:
- Source table  : dim_voucher_catalog
- Inclusion mode: GRAPH_CORE
- Graph entity  : Voucher
- Freshness field: created_at (declared but not used — full refresh)
- Declared PK   : None (voucher_key treated as stable de facto key)
"""

from __future__ import annotations

from app.contracts.warehouse_rows import WarehouseRow
from app.extractors.base import BaseExtractor
from app.schemas.warehouse.voucher_catalog import (
    FRESHNESS_FIELD,
    INCLUSION_MODE,
    PRIMARY_KEYS,
    SOURCE_NAME,
    VoucherCatalogRow,
)


class VoucherCatalogExtractor(BaseExtractor):
    """
    Extractor for dim_voucher_catalog.

    Full-refresh strategy:
    - supports_incremental = False
    - watermark is never read or written for this source
    - every run extracts the full voucher catalog

    Rationale for full refresh over incremental:
        Aggregate columns (total_purchases, total_redeemed, total_coins_spent,
        stock_remaining, last_purchase_date) update in-place as purchases
        occur. An incremental filter on created_at would silently miss all
        aggregate updates on existing catalog entries. Full refresh keeps
        stock and redemption aggregates current across all vouchers.

    No declared PK:
    - voucher_key is treated as the stable de facto key.
      Deduplication is a transformer concern.

    Ordering:
    - stable sort by voucher_key enables reliable diff-based change detection
      across repeated full-refresh runs.
    """

    source_name: str = SOURCE_NAME
    schema_row_class: type[WarehouseRow] = VoucherCatalogRow
    inclusion_mode: str = INCLUSION_MODE
    freshness_field: str | None = FRESHNESS_FIELD     
    primary_key_fields: tuple[str, ...] = PRIMARY_KEYS
    default_chunk_size: int = 1000                    
    supports_incremental: bool = False

    # ── Source column contract ────────────────────────────────────────────────

    def get_source_columns(self) -> tuple[str, ...]:
        """
        Return the explicit ordered source columns for dim_voucher_catalog.

        These columns must stay aligned with VoucherCatalogRow.from_row().
        Adding or removing a column here requires a matching change in
        the schema row dataclass.

        No-PK note:
            voucher_key has no declared PK constraint. Preserved exactly as
            sourced; deduplication belongs to the transformer layer.

        Sensitive field note:
            voucher_code is the user-facing redemption code. Extracted from
            source truth; must not propagate to graph DTOs or API responses.

        Aggregate fields note:
            total_purchases, total_redeemed, total_coins_spent, stock_remaining,
            last_purchase_date — current-state aggregates updated in-place.
            These are the primary reason for full-refresh over incremental.
        """
        return (
            "voucher_key",
            "advertiser_id",
            "advertiser_name",
            "voucher_title",
            "voucher_description",
            "voucher_terms",
            "tracking_url",
            "voucher_code",           # sensitive — must not reach graph/API boundary
            "acquisition_type",
            "is_exclusive",
            "coin_cost",
            "expiry_date_utc",
            "is_active",
            "voucher_image",
            "total_purchases",        # running aggregate — updated in-place
            "total_redeemed",         # running aggregate — updated in-place
            "total_coins_spent",      # running aggregate — updated in-place
            "first_purchase_date",
            "last_purchase_date",     # running aggregate — updated in-place
            "created_at",
            "stock_initial",
            "stock_total",
            "stock_remaining",        # running aggregate — decrements on purchase
        )

    # ── Query construction ────────────────────────────────────────────────────

    def build_base_query(self) -> str:
        """
        Return the base SELECT for dim_voucher_catalog.

        No WHERE clause is included; the catalog is always fully refreshed
        to keep stock and redemption aggregates current.
        """
        columns = ",\n    ".join(self.get_source_columns())
        return f"""
SELECT
    {columns}
FROM {self.source_name}
""".strip()

    def build_incremental_clause(self, watermark_value: str | None) -> str:
        """
        Always returns an empty string.

        dim_voucher_catalog uses full-refresh semantics. Although created_at
        is declared as the freshness field in the schema module, filtering by
        it would silently miss aggregate updates on existing catalog entries.
        This override makes the no-incremental intent explicit.
        """
        return ""

    def build_order_by_clause(self) -> str:
        """
        Return stable deterministic ordering for dim_voucher_catalog.

        Ordered by voucher_key (the stable de facto key) for consistent,
        diff-comparable output across repeated full-refresh runs.
        """
        return "\nORDER BY voucher_key"

    def build_pagination_clause(self, limit: int, offset: int) -> str:
        """
        Return LIMIT/OFFSET pagination clause.
        """
        return "\nLIMIT %(limit)s OFFSET %(offset)s"