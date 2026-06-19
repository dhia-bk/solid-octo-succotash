"""
Extractor for the dim_subscription_products warehouse source.

Purpose:
- Extract subscription tier catalog rows from dim_subscription_products,
  including subscription_type_id, name, price, duration, and all permission
  flags.
- Full-refresh strategy — the source has no timestamp column in the DWH, so
  every pipeline run extracts all rows deterministically.
- Return typed SubscriptionProductsRow instances wrapped in ExtractorBatch.

Source characteristics:
    dim_subscription_products is a small, stable permission catalog. Each row
    defines a subscription tier and its associated feature entitlements (early
    prediction, predictive algorithm, group/private chat creation, private
    league creation, prediction editing). The catalog changes infrequently —
    only when new subscription tiers are introduced or permission grants are
    revised — and has no mutation timestamp to drive incremental extraction.

    Full refresh is both the only possible strategy (no timestamp) and the
    correct one — the catalog is tiny (typically fewer than ten rows) and
    permission flag changes must be captured in full to ensure the graph
    reflects the current entitlement structure.

    Permission flags are TINYINT 0/1 in the DWH and are stored as int | None
    per the project-wide convention (not bool). Downstream layers that need
    boolean semantics must apply an explicit comparison.

Design rules:
- subscription_type_id is an INTEGER PK; stored as int. Ordered by this
  field for stable, diff-comparable full-refresh output.
- subscription_price is DECIMAL(10,2) in the DWH; stored as float | None.
  Downstream financial displays should use precision-safe formatting.
- All has_* columns are TINYINT permission flags; stored as int | None.
  None indicates the flag is not defined for this tier (treated as no
  permission by downstream layers).
- No graph logic, canonicalization, or enrichment is applied here.

Source schema:
- Source table  : dim_subscription_products
- Inclusion mode: GRAPH_CORE
- Graph entity  : SubscriptionProduct
- Freshness field: None (static dimension)
"""

from __future__ import annotations

from app.contracts.warehouse_rows import WarehouseRow
from app.extractors.base import BaseExtractor
from app.schemas.warehouse.subscription_products import (
    FRESHNESS_FIELD,
    INCLUSION_MODE,
    PRIMARY_KEYS,
    SOURCE_NAME,
    SubscriptionProductsRow,
)


class SubscriptionProductsExtractor(BaseExtractor):
    """
    Extractor for dim_subscription_products.

    Full-refresh strategy:
    - supports_incremental = False
    - freshness_field      = None
    - watermark is never read or written for this source
    - every run extracts the full subscription tier catalog

    Permission flag semantics:
    - All has_* columns are TINYINT 0/1 flags stored as int | None.
    - Downstream layers must apply explicit boolean comparison; do not
      treat None as False without checking the tier definition.

    Ordering:
    - stable sort by subscription_type_id (integer PK) ensures idempotent
      output across repeated full-refresh runs.
    """

    source_name: str = SOURCE_NAME
    schema_row_class: type[WarehouseRow] = SubscriptionProductsRow
    inclusion_mode: str = INCLUSION_MODE
    freshness_field: str | None = FRESHNESS_FIELD     # None — static dimension
    primary_key_fields: tuple[str, ...] = PRIMARY_KEYS
    default_chunk_size: int = 100                     # catalog is tiny;
                                                      # typically < 10 rows
    supports_incremental: bool = False

    # ── Source column contract ────────────────────────────────────────────────

    def get_source_columns(self) -> tuple[str, ...]:
        """
        Return the explicit ordered source columns for dim_subscription_products.

        These columns must stay aligned with SubscriptionProductsRow.from_row().
        Adding or removing a column here requires a matching change in
        the schema row dataclass.

        Permission flag note:
            All has_* columns are TINYINT 0/1 in the DWH; stored as int | None.
            A change to any flag value on any tier must be captured on the
            next full-refresh run and propagated to all User nodes via the
            SUBSCRIBED_TO edge properties.

        subscription_price note:
            DECIMAL(10,2) in the DWH; stored as float | None. Display
            formatting and currency conversion belong to downstream layers.
        """
        return (
            "subscription_type_id",
            "subscription_name",
            "subscription_price",                   # DECIMAL(10,2) — float | None
            "duration_in_days",
            "has_early_prediction_permission",       # TINYINT permission flag
            "has_predictive_algorithm_permission",   # TINYINT permission flag
            "has_group_chat_create_permission",      # TINYINT permission flag
            "has_private_chat_create_permission",    # TINYINT permission flag
            "has_private_league_create_permission",  # TINYINT permission flag
            "has_prediction_edit_permission",        # TINYINT permission flag
        )

    # ── Query construction ────────────────────────────────────────────────────

    def build_base_query(self) -> str:
        """
        Return the base SELECT for dim_subscription_products.

        No WHERE clause is included; the catalog is always fully refreshed
        because it has no mutation timestamp.
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

        dim_subscription_products has no freshness timestamp and is never
        extracted incrementally. This override makes the intent explicit and
        prevents accidental watermark injection during future refactoring.
        """
        return ""

    def build_order_by_clause(self) -> str:
        """
        Return stable deterministic ordering for dim_subscription_products.

        Ordered by subscription_type_id (integer PK). Integer sort order is
        naturally correct without CAST. Consistent PK ordering across all
        full-refresh runs enables reliable diff-based permission change
        detection in downstream layers.
        """
        return "\nORDER BY subscription_type_id"

    def build_pagination_clause(self, limit: int, offset: int) -> str:
        """
        Return LIMIT/OFFSET pagination clause.
        """
        return "\nLIMIT %(limit)s OFFSET %(offset)s"