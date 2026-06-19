"""
Extractor for the fct_partner_reward_inventory warehouse source.

Purpose:
- Extract partner reward inventory event rows from fct_partner_reward_inventory,
  including stock levels, discount price, event metadata, and linkage to
  the partner reward catalog via reward_key.
- Incremental strategy using event_created_at_utc as the watermark.
- Return typed PartnerRewardInventoryRow instances wrapped in ExtractorBatch.

Watermark field — event_created_at_utc vs created_at_utc:
    The schema module declares FRESHNESS_FIELD = "created_at_utc". The source
    table carries two timestamp fields: created_at_utc (the row write time)
    and event_created_at_utc (the business event time at the originating
    system). The plan explicitly specifies event_created_at_utc as the
    watermark field, which is the correct choice for an event-driven enrichment
    source — it aligns the watermark with the business event timeline rather
    than the ETL write time. Both timestamps are preserved in the column list.

Source characteristics:
    fct_partner_reward_inventory is an event log of stock-level changes and
    inventory updates for partner rewards. Each row represents a distinct
    inventory event (e.g. stock top-up, price change, expiry update). Rows
    are append-only; event_created_at_utc is the authoritative event timestamp.

    reward_key is the FK to dim_partner_reward_catalog. It is preserved
    exactly so the transformer can enrich existing PartnerReward nodes rather
    than creating new ones.

discount_price handling:
    discount_price is INTEGER in the DWH, stored in base currency units
    (pence, cents, or equivalent). It is stored as int | None at this layer;
    conversion to display units (e.g. dividing by 100 for USD) is the
    transformer's responsibility, not the extractor's.

No declared primary key:
    inventory_event_id is VARCHAR(100) with no PK constraint in the DWH.
    It is treated as the stable de facto event identity at extraction time.
    Deduplication is a transformer concern.

Design rules:
- event_created_at_utc is the watermark; created_at_utc is preserved as
  the ETL write timestamp for auditing purposes.
- discount_price is stored as int (base units); unit conversion belongs
  to the transformer.
- reward_key is the catalog FK; must be preserved exactly for PartnerReward
  node enrichment routing.
- No graph logic, canonicalization, or enrichment is applied here.

Source schema:
- Source table  : fct_partner_reward_inventory
- Inclusion mode: GRAPH_ENRICHMENT
- Graph entity  : PartnerReward (enrichment)
- Schema freshness field: created_at_utc (declared)
- Extractor watermark  : event_created_at_utc (preferred — business event time)
- Declared PK   : None (inventory_event_id treated as stable de facto key)
"""

from __future__ import annotations

from app.contracts.warehouse_rows import WarehouseRow
from app.extractors.base import BaseExtractor
from app.schemas.warehouse.partner_reward_inventory import (
    INCLUSION_MODE,
    PRIMARY_KEYS,
    SOURCE_NAME,
    PartnerRewardInventoryRow,
)

# Watermark field used by this extractor — intentionally different from the
# schema-declared FRESHNESS_FIELD ("created_at_utc"). See module docstring.
_WATERMARK_FIELD: str = "event_created_at_utc"


class PartnerRewardInventoryExtractor(BaseExtractor):
    """
    Extractor for fct_partner_reward_inventory.

    Incremental strategy:
    - watermark field: event_created_at_utc (not schema-declared created_at_utc)
    - ordering: event_created_at_utc, inventory_event_id

    Event-time watermark:
    - event_created_at_utc aligns the watermark with the business event
      timeline, which is the correct reference point for inventory event
      processing. created_at_utc (ETL write time) is preserved for auditing.

    Append-oriented semantics:
    - Inventory events are written once and not updated. Incremental
      extraction is therefore complete and correct with no mutation window.

    No declared PK:
    - inventory_event_id is treated as the stable de facto event key.
      Deduplication is a transformer concern.
    """

    source_name: str = SOURCE_NAME
    schema_row_class: type[WarehouseRow] = PartnerRewardInventoryRow
    inclusion_mode: str = INCLUSION_MODE
    freshness_field: str | None = _WATERMARK_FIELD    # event_created_at_utc
    primary_key_fields: tuple[str, ...] = PRIMARY_KEYS
    default_chunk_size: int = 5000
    supports_incremental: bool = True

    # ── Source column contract ────────────────────────────────────────────────

    def get_source_columns(self) -> tuple[str, ...]:
        """
        Return the explicit ordered source columns for fct_partner_reward_inventory.

        These columns must stay aligned with PartnerRewardInventoryRow.from_row().
        Adding or removing a column here requires a matching change in
        the schema row dataclass.

        Watermark note:
            event_created_at_utc is the extractor watermark (business event
            time). created_at_utc is the ETL write timestamp; preserved for
            auditing and lineage purposes.

        discount_price note:
            INTEGER in the DWH (base currency units — pence/cents). Stored
            as int | None here. Unit conversion to display currency belongs
            to the transformer.

        reward_key note:
            FK to dim_partner_reward_catalog. Preserved exactly for
            PartnerReward node enrichment routing.

        source_sequence note:
            Ordering signal from the originating event stream. Preserved
            for the transformer to apply events in the correct sequence
            when multiple events share the same event_created_at_utc.
        """
        return (
            "inventory_event_id",
            "reward_key",               # FK to dim_partner_reward_catalog
            "partner_name",
            "reward_title",
            "stock_total",
            "discount_price",           # INTEGER base units — unit convert in transformer
            "expiration_date_utc",
            "redemption_instructions",
            "conditions",
            "created_at_utc",           # ETL write timestamp — auditing/lineage
            "created_date_key",         # INTEGER partition label; str | None
            "event_id",
            "event_type",
            "source_sequence",          # event ordering signal within same timestamp
            "event_created_at_utc",     # extractor watermark field — business event time
        )

    # ── Query construction ────────────────────────────────────────────────────

    def build_base_query(self) -> str:
        """
        Return the base SELECT for fct_partner_reward_inventory without
        incremental filtering.

        The incremental clause
        (WHERE event_created_at_utc > %(watermark_value)s) is appended by
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
        Build the incremental filter using event_created_at_utc.

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
        Return stable deterministic ordering for fct_partner_reward_inventory.

        event_created_at_utc first — aligns with watermark advancement and
        clusters output by business event time.

        inventory_event_id second — VARCHAR de facto key; breaks ties within
        the same event timestamp bucket deterministically.
        """
        return "\nORDER BY event_created_at_utc, inventory_event_id"

    def build_pagination_clause(self, limit: int, offset: int) -> str:
        """
        Return LIMIT/OFFSET pagination clause.
        """
        return "\nLIMIT %(limit)s OFFSET %(offset)s"