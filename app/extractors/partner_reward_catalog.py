"""
Extractor for the dim_partner_reward_catalog warehouse source.

Purpose:
- Extract partner reward catalog rows from dim_partner_reward_catalog,
  including reward_key, partner_name, reward_title, coin cost, real-world
  value, stock levels, validity range, and active state.
- Full-refresh strategy — aggregate columns (total_redemptions,
  stock_remaining) update in-place as redemptions occur, making incremental
  extraction by created_at insufficient to keep catalog state current.
- Return typed PartnerRewardCatalogRow instances wrapped in ExtractorBatch.

Full-refresh rationale:
    dim_partner_reward_catalog follows the same pattern as dim_voucher_catalog:
    it is a current-state dimension with running aggregate columns. stock_remaining
    decrements and total_redemptions increments on every redemption event.
    An incremental filter on created_at would correctly capture new reward
    entries but silently miss all stock and redemption aggregate updates on
    existing catalog entries. Full refresh keeps all catalog rows current.
    The catalog is bounded in size (limited by the number of active partner
    rewards on offer), so full refresh cost is low.

No declared primary key:
    reward_key has no PK constraint in the DWH. It is the stable de facto
    catalog identity at extraction time; deduplication is a transformer concern.
    The extractor preserves reward_key exactly as sourced and must not attempt
    to synthesize or normalize it.

DATE column handling:
    valid_from and valid_until are DATE columns in the DWH, stored as
    str | None in PartnerRewardCatalogRow to preserve date-only semantics
    without timezone coercion. No warehouse_value_to_utc_datetime conversion
    is applied to these two fields.

Design rules:
- reward_key must be preserved exactly as sourced (stable de facto key).
- real_world_value_usd is DECIMAL(10,2) in the DWH; stored as float | None.
  Downstream financial comparisons should use precision-safe arithmetic.
- is_active is a TINYINT 0/1 flag; can change as rewards are activated or
  deactivated — correctly captured on every full-refresh run.
- No graph logic, canonicalization, or enrichment is applied here.

Source schema:
- Source table  : dim_partner_reward_catalog
- Inclusion mode: GRAPH_CORE
- Graph entity  : PartnerReward
- Freshness field: created_at (declared but not used — full refresh)
- Declared PK   : None (reward_key treated as stable de facto key)
"""

from __future__ import annotations

from app.contracts.warehouse_rows import WarehouseRow
from app.extractors.base import BaseExtractor
from app.schemas.warehouse.partner_reward_catalog import (
    FRESHNESS_FIELD,
    INCLUSION_MODE,
    PRIMARY_KEYS,
    SOURCE_NAME,
    PartnerRewardCatalogRow,
)


class PartnerRewardCatalogExtractor(BaseExtractor):
    """
    Extractor for dim_partner_reward_catalog.

    Full-refresh strategy:
    - supports_incremental = False
    - watermark is never read or written for this source
    - every run extracts the full partner reward catalog

    Rationale for full refresh over incremental:
        total_redemptions and stock_remaining update in-place on every
        redemption event. An incremental filter on created_at would
        silently miss these aggregate updates on existing catalog entries.

    No declared PK:
    - reward_key is treated as the stable de facto catalog key.
      Deduplication is a transformer concern.

    Ordering:
    - stable sort by reward_key enables reliable diff-based change detection
      across repeated full-refresh runs.
    """

    source_name: str = SOURCE_NAME
    schema_row_class: type[WarehouseRow] = PartnerRewardCatalogRow
    inclusion_mode: str = INCLUSION_MODE
    freshness_field: str | None = FRESHNESS_FIELD     
    primary_key_fields: tuple[str, ...] = PRIMARY_KEYS
    default_chunk_size: int = 1000                    
    supports_incremental: bool = False

    # ── Source column contract ────────────────────────────────────────────────

    def get_source_columns(self) -> tuple[str, ...]:
        """
        Return the explicit ordered source columns for dim_partner_reward_catalog.

        These columns must stay aligned with PartnerRewardCatalogRow.from_row().
        Adding or removing a column here requires a matching change in
        the schema row dataclass.

        No-PK note:
            reward_key has no declared PK constraint. Preserved exactly as
            sourced; deduplication belongs to the transformer layer.

        DATE column note:
            valid_from, valid_until — DATE columns in the DWH; from_row()
            stores as str | None to preserve date-only semantics without
            timezone coercion. Do not apply warehouse_value_to_utc_datetime.

        Aggregate fields note:
            total_redemptions, stock_remaining — current-state aggregates
            updated in-place on every redemption. Primary reason for
            full-refresh over incremental.

        Decimal field note:
            real_world_value_usd — DECIMAL(10,2); stored as float | None.
            Downstream financial comparisons should use precision-safe
            arithmetic.
        """
        return (
            "reward_key",
            "partner_name",
            "reward_title",
            "reward_type",
            "coin_cost",
            "real_world_value_usd",       # DECIMAL(10,2) — float | None
            "stock_quantity",
            "total_redemptions",          # running aggregate — updated in-place
            "stock_remaining",            # running aggregate — decrements on redemption
            "redemption_instructions",
            "terms_and_conditions",
            "valid_from",                 # DATE column — stored as str | None
            "valid_until",                # DATE column — stored as str | None
            "is_active",
            "created_at",
            "stock_initial",
            "stock_total",
        )

    # ── Query construction ────────────────────────────────────────────────────

    def build_base_query(self) -> str:
        """
        Return the base SELECT for dim_partner_reward_catalog.

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

        dim_partner_reward_catalog uses full-refresh semantics. Although
        created_at is declared as the freshness field in the schema module,
        filtering by it would silently miss aggregate updates on existing
        catalog entries. This override makes the no-incremental intent explicit.
        """
        return ""

    def build_order_by_clause(self) -> str:
        """
        Return stable deterministic ordering for dim_partner_reward_catalog.

        Ordered by reward_key (the stable de facto catalog key) for consistent,
        diff-comparable output across repeated full-refresh runs.
        """
        return "\nORDER BY reward_key"

    def build_pagination_clause(self, limit: int, offset: int) -> str:
        """
        Return LIMIT/OFFSET pagination clause.
        """
        return "\nLIMIT %(limit)s OFFSET %(offset)s"