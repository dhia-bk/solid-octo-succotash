"""
Warehouse schema for fct_partner_reward_inventory.

Source table: fct_partner_reward_inventory
Domain: economy
Inclusion mode: GRAPH_ENRICHMENT — enriches PartnerReward nodes
Graph entity: PartnerReward (enrichment; does not create a new node type)
Freshness field: created_at_utc

Partner reward stock and event-driven updates. Enriches existing PartnerReward
nodes with current stock levels and inventory event data.

DWH type notes:
    inventory_event_id — VARCHAR(100); no declared PK constraint; str.
    discount_price     — INTEGER in DWH (stored in pence/cents or base units);
                         int | None (spec suggested float — DWH wins; semantic
                         interpretation is the transformer's responsibility).
    created_date_key   — INTEGER partition key; str | None.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.core.constants import GRAPH_ENRICHMENT, PARTNER_REWARD
from app.core.ids import normalize_nullable_string_id, normalize_string_id
from app.core.time import warehouse_value_to_utc_datetime

# ── Module-level constants ────────────────────────────────────────────────────

SOURCE_NAME: str = "fct_partner_reward_inventory"
INCLUSION_MODE: str = GRAPH_ENRICHMENT
PRIMARY_KEYS: tuple[str, ...] = ("inventory_event_id",)
FRESHNESS_FIELD: str | None = "created_at_utc"
GRAPH_ENTITY_MAPPINGS: tuple[str, ...] = (PARTNER_REWARD,)


# ── Row shape ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class PartnerRewardInventoryRow:
    """
    Typed row shape for fct_partner_reward_inventory.

    inventory_event_id is VARCHAR(100) with no PK constraint; treated as
    the stable de facto key.

    discount_price is INTEGER in the DWH (base currency units);
    int | None at this layer. The transformer converts to display units.

    created_date_key is an INTEGER partition key; str | None.
    """

    inventory_event_id: str
    reward_key: str | None
    partner_name: str | None
    reward_title: str | None
    stock_total: int | None
    discount_price: int | None
    expiration_date_utc: datetime | None
    redemption_instructions: str | None
    conditions: str | None
    created_at_utc: datetime | None
    created_date_key: str | None
    event_id: str | None
    event_type: str | None
    source_sequence: int | None
    event_created_at_utc: datetime | None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> PartnerRewardInventoryRow:
        """Normalize a raw warehouse row into a typed PartnerRewardInventoryRow."""
        return cls(
            inventory_event_id=normalize_string_id(row["inventory_event_id"], field_name="inventory_event_id"),
            reward_key=normalize_nullable_string_id(row.get("reward_key"), field_name="reward_key"),
            partner_name=row.get("partner_name"),
            reward_title=row.get("reward_title"),
            stock_total=int(row["stock_total"]) if row.get("stock_total") is not None else None,
            discount_price=int(row["discount_price"]) if row.get("discount_price") is not None else None,
            expiration_date_utc=warehouse_value_to_utc_datetime(row.get("expiration_date_utc")),
            redemption_instructions=row.get("redemption_instructions"),
            conditions=row.get("conditions"),
            created_at_utc=warehouse_value_to_utc_datetime(row.get("created_at_utc")),
            created_date_key=str(row["created_date_key"]) if row.get("created_date_key") is not None else None,
            event_id=normalize_nullable_string_id(row.get("event_id"), field_name="event_id"),
            event_type=row.get("event_type"),
            source_sequence=int(row["source_sequence"]) if row.get("source_sequence") is not None else None,
            event_created_at_utc=warehouse_value_to_utc_datetime(row.get("event_created_at_utc")),
        )
