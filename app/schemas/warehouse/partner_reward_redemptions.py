"""
Warehouse schema for fct_partner_reward_redemptions.

Source table: fct_partner_reward_redemptions
Domain: economy
Inclusion mode: GRAPH_CORE — feeds relationship creation
Graph entity: REDEEMED relationship (User → PartnerReward)
Freshness field: redeemed_at_utc

Partner reward redemption events. No declared PK constraint; redemption_id
treated as the stable de facto key. Feeds REDEEMED edge properties.

PII WARNING:
    user_email is a PII field. This field must NOT be written to graph
    properties or logs. The transformer must drop or hash this field before
    any downstream processing.

DWH type notes:
    redemption_date_key — INTEGER partition key; str | None.
    transaction_amount  — DECIMAL(10,2); float | None.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.core.constants import GRAPH_CORE, REDEEMED
from app.core.ids import normalize_nullable_string_id, normalize_string_id
from app.core.time import warehouse_value_to_utc_datetime

# ── Module-level constants ────────────────────────────────────────────────────

SOURCE_NAME: str = "fct_partner_reward_redemptions"
INCLUSION_MODE: str = GRAPH_CORE
PRIMARY_KEYS: tuple[str, ...] = ("redemption_id",)
FRESHNESS_FIELD: str | None = "redeemed_at_utc"
GRAPH_ENTITY_MAPPINGS: tuple[str, ...] = (REDEEMED,)


# ── Row shape ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class PartnerRewardRedemptionsRow:
    """
    Typed row shape for fct_partner_reward_redemptions.

    PII fields — must NOT be written to the graph or logs:
        user_email

    redemption_id has no PK constraint; treated as the stable de facto key.
    redemption_date_key is an INTEGER partition key; str | None.
    transaction_amount is DECIMAL(10,2); float | None.
    """

    redemption_id: str
    reward_key: str | None
    partner_name: str | None
    reward_title: str | None
    user_id: str | None
    user_email: str | None
    quantity: int | None
    transaction_amount: float | None
    redeemed_at_utc: datetime | None
    redemption_date_key: str | None
    event_id: str | None
    event_type: str | None
    source_sequence: int | None
    event_created_at_utc: datetime | None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> PartnerRewardRedemptionsRow:
        """Normalize a raw warehouse row into a typed PartnerRewardRedemptionsRow."""
        return cls(
            redemption_id=normalize_string_id(row["redemption_id"], field_name="redemption_id"),
            reward_key=normalize_nullable_string_id(row.get("reward_key"), field_name="reward_key"),
            partner_name=row.get("partner_name"),
            reward_title=row.get("reward_title"),
            user_id=normalize_nullable_string_id(row.get("user_id"), field_name="user_id"),
            user_email=row.get("user_email"),  # PII — transformer must drop/hash before graph load
            quantity=int(row["quantity"]) if row.get("quantity") is not None else None,
            transaction_amount=float(row["transaction_amount"]) if row.get("transaction_amount") is not None else None,
            redeemed_at_utc=warehouse_value_to_utc_datetime(row.get("redeemed_at_utc")),
            redemption_date_key=str(row["redemption_date_key"]) if row.get("redemption_date_key") is not None else None,
            event_id=normalize_nullable_string_id(row.get("event_id"), field_name="event_id"),
            event_type=row.get("event_type"),
            source_sequence=int(row["source_sequence"]) if row.get("source_sequence") is not None else None,
            event_created_at_utc=warehouse_value_to_utc_datetime(row.get("event_created_at_utc")),
        )
