"""
Warehouse schema for dim_partner_reward_catalog.

Source table: dim_partner_reward_catalog
Domain: economy
Inclusion mode: GRAPH_CORE — direct graph node creation
Graph entity: PartnerReward
Freshness field: created_at

Partner reward catalog dimension. No declared PK constraint; reward_key
treated as the stable de facto key. Feeds PartnerReward nodes and REDEEMED
relationship (User → PartnerReward).

DWH type notes:
    valid_from, valid_until — DATE columns; str | None (date-only values;
        not converted to datetime to avoid spurious timezone shifts).
    real_world_value_usd   — DECIMAL(10,2); float | None.
    is_active              — TINYINT 0/1.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.core.constants import GRAPH_CORE, PARTNER_REWARD
from app.core.ids import normalize_string_id
from app.core.time import warehouse_value_to_utc_datetime

# ── Module-level constants ────────────────────────────────────────────────────

SOURCE_NAME: str = "dim_partner_reward_catalog"
INCLUSION_MODE: str = GRAPH_CORE
PRIMARY_KEYS: tuple[str, ...] = ("reward_key",)
FRESHNESS_FIELD: str | None = "created_at"
GRAPH_ENTITY_MAPPINGS: tuple[str, ...] = (PARTNER_REWARD,)


# ── Row shape ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class PartnerRewardCatalogRow:
    """
    Typed row shape for dim_partner_reward_catalog.

    TINYINT fields (0/1 integers, not booleans in the DWH):
        is_active

    valid_from and valid_until are DATE columns; stored as str | None to
    preserve date-only semantics without timezone coercion.
    reward_key has no PK constraint; treated as the stable de facto key.
    """

    reward_key: str
    partner_name: str | None
    reward_title: str | None
    reward_type: str | None
    coin_cost: int | None
    real_world_value_usd: float | None
    stock_quantity: int | None
    total_redemptions: int | None
    stock_remaining: int | None
    redemption_instructions: str | None
    terms_and_conditions: str | None
    valid_from: str | None
    valid_until: str | None
    is_active: int | None
    created_at: datetime | None
    stock_initial: int | None
    stock_total: int | None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> PartnerRewardCatalogRow:
        """Normalize a raw warehouse row into a typed PartnerRewardCatalogRow."""
        return cls(
            reward_key=normalize_string_id(row["reward_key"], field_name="reward_key"),
            partner_name=row.get("partner_name"),
            reward_title=row.get("reward_title"),
            reward_type=row.get("reward_type"),
            coin_cost=int(row["coin_cost"]) if row.get("coin_cost") is not None else None,
            real_world_value_usd=float(row["real_world_value_usd"]) if row.get("real_world_value_usd") is not None else None,
            stock_quantity=int(row["stock_quantity"]) if row.get("stock_quantity") is not None else None,
            total_redemptions=int(row["total_redemptions"]) if row.get("total_redemptions") is not None else None,
            stock_remaining=int(row["stock_remaining"]) if row.get("stock_remaining") is not None else None,
            redemption_instructions=row.get("redemption_instructions"),
            terms_and_conditions=row.get("terms_and_conditions"),
            valid_from=str(row["valid_from"]) if row.get("valid_from") is not None else None,
            valid_until=str(row["valid_until"]) if row.get("valid_until") is not None else None,
            is_active=int(row["is_active"]) if row.get("is_active") is not None else None,
            created_at=warehouse_value_to_utc_datetime(row.get("created_at")),
            stock_initial=int(row["stock_initial"]) if row.get("stock_initial") is not None else None,
            stock_total=int(row["stock_total"]) if row.get("stock_total") is not None else None,
        )
