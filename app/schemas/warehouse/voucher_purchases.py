"""
Warehouse schema for fct_voucher_purchases.

Source table: fct_voucher_purchases
Domain: economy
Inclusion mode: GRAPH_CORE — feeds relationship creation
Graph entity: PURCHASED relationship (User → Voucher)
Freshness field: purchase_date_utc

Voucher purchase events. No declared PK constraint; purchase_id treated
as the stable de facto key. Feeds PURCHASED edge properties: coin cost,
purchase date, redemption status.

DWH type notes:
    purchase_date_key, expiry_date_key, used_date_key — INTEGER partition
        keys; all exposed as str | None.
    is_used — TINYINT 0/1.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.core.constants import GRAPH_CORE, PURCHASED
from app.core.ids import normalize_nullable_string_id, normalize_string_id
from app.core.time import warehouse_value_to_utc_datetime

# ── Module-level constants ────────────────────────────────────────────────────

SOURCE_NAME: str = "fct_voucher_purchases"
INCLUSION_MODE: str = GRAPH_CORE
PRIMARY_KEYS: tuple[str, ...] = ("purchase_id",)
FRESHNESS_FIELD: str | None = "purchase_date_utc"
GRAPH_ENTITY_MAPPINGS: tuple[str, ...] = (PURCHASED,)


# ── Row shape ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class VoucherPurchasesRow:
    """
    Typed row shape for fct_voucher_purchases.

    TINYINT fields (0/1 integers, not booleans in the DWH):
        is_used

    All *_date_key fields are INTEGER partition keys; str | None.
    purchase_id has no PK constraint; treated as stable de facto key.
    """

    purchase_id: str
    user_id: str | None
    voucher_id: str | None
    voucher_code: str | None
    coin_cost: int | None
    purchase_date_utc: datetime | None
    purchase_date_key: str | None
    expiry_date_utc: datetime | None
    expiry_date_key: str | None
    is_used: int | None
    used_date_utc: datetime | None
    used_date_key: str | None
    acquisition_type: str | None
    ad_reward_token: str | None
    ad_unit_id: str | None
    days_to_redemption: int | None
    voucher_status: str | None
    voucher_key: str | None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> VoucherPurchasesRow:
        """Normalize a raw warehouse row into a typed VoucherPurchasesRow."""
        return cls(
            purchase_id=normalize_string_id(row["purchase_id"], field_name="purchase_id"),
            user_id=normalize_nullable_string_id(row.get("user_id"), field_name="user_id"),
            voucher_id=normalize_nullable_string_id(row.get("voucher_id"), field_name="voucher_id"),
            voucher_code=row.get("voucher_code"),
            coin_cost=int(row["coin_cost"]) if row.get("coin_cost") is not None else None,
            purchase_date_utc=warehouse_value_to_utc_datetime(row.get("purchase_date_utc")),
            purchase_date_key=str(row["purchase_date_key"]) if row.get("purchase_date_key") is not None else None,
            expiry_date_utc=warehouse_value_to_utc_datetime(row.get("expiry_date_utc")),
            expiry_date_key=str(row["expiry_date_key"]) if row.get("expiry_date_key") is not None else None,
            is_used=int(row["is_used"]) if row.get("is_used") is not None else None,
            used_date_utc=warehouse_value_to_utc_datetime(row.get("used_date_utc")),
            used_date_key=str(row["used_date_key"]) if row.get("used_date_key") is not None else None,
            acquisition_type=row.get("acquisition_type"),
            ad_reward_token=row.get("ad_reward_token"),
            ad_unit_id=row.get("ad_unit_id"),
            days_to_redemption=int(row["days_to_redemption"]) if row.get("days_to_redemption") is not None else None,
            voucher_status=row.get("voucher_status"),
            voucher_key=normalize_nullable_string_id(row.get("voucher_key"), field_name="voucher_key"),
        )
