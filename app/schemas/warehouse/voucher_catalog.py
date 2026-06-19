"""
Warehouse schema for dim_voucher_catalog.

Source table: dim_voucher_catalog
Domain: economy
Inclusion mode: GRAPH_CORE — direct graph node creation
Graph entity: Voucher
Freshness field: created_at

Voucher catalog dimension. No declared PK constraint; voucher_key treated
as the stable de facto key. Feeds Voucher nodes and PURCHASED relationship
(User → Voucher).

DWH type note:
    advertiser_id  — INTEGER in DWH; int | None (spec suggested str).
    is_exclusive, is_active — TINYINT 0/1 flags.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.core.constants import GRAPH_CORE, VOUCHER
from app.core.ids import normalize_string_id
from app.core.time import warehouse_value_to_utc_datetime

# ── Module-level constants ────────────────────────────────────────────────────

SOURCE_NAME: str = "dim_voucher_catalog"
INCLUSION_MODE: str = GRAPH_CORE
PRIMARY_KEYS: tuple[str, ...] = ("voucher_key",)
FRESHNESS_FIELD: str | None = "created_at"
GRAPH_ENTITY_MAPPINGS: tuple[str, ...] = (VOUCHER,)


# ── Row shape ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class VoucherCatalogRow:
    """
    Typed row shape for dim_voucher_catalog.

    TINYINT fields (0/1 integers, not booleans in the DWH):
        is_exclusive
        is_active

    advertiser_id is INTEGER in the DWH; int | None.
    voucher_key has no PK constraint; treated as the stable de facto key.
    """

    voucher_key: str
    advertiser_id: int | None
    advertiser_name: str | None
    voucher_title: str | None
    voucher_description: str | None
    voucher_terms: str | None
    tracking_url: str | None
    voucher_code: str | None
    acquisition_type: str | None
    is_exclusive: int | None
    coin_cost: int | None
    expiry_date_utc: datetime | None
    is_active: int | None
    voucher_image: str | None
    total_purchases: int | None
    total_redeemed: int | None
    total_coins_spent: int | None
    first_purchase_date: datetime | None
    last_purchase_date: datetime | None
    created_at: datetime | None
    stock_initial: int | None
    stock_total: int | None
    stock_remaining: int | None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> VoucherCatalogRow:
        """Normalize a raw warehouse row into a typed VoucherCatalogRow."""
        return cls(
            voucher_key=normalize_string_id(row["voucher_key"], field_name="voucher_key"),
            advertiser_id=int(row["advertiser_id"]) if row.get("advertiser_id") is not None else None,
            advertiser_name=row.get("advertiser_name"),
            voucher_title=row.get("voucher_title"),
            voucher_description=row.get("voucher_description"),
            voucher_terms=row.get("voucher_terms"),
            tracking_url=row.get("tracking_url"),
            voucher_code=row.get("voucher_code"),
            acquisition_type=row.get("acquisition_type"),
            is_exclusive=int(row["is_exclusive"]) if row.get("is_exclusive") is not None else None,
            coin_cost=int(row["coin_cost"]) if row.get("coin_cost") is not None else None,
            expiry_date_utc=warehouse_value_to_utc_datetime(row.get("expiry_date_utc")),
            is_active=int(row["is_active"]) if row.get("is_active") is not None else None,
            voucher_image=row.get("voucher_image"),
            total_purchases=int(row["total_purchases"]) if row.get("total_purchases") is not None else None,
            total_redeemed=int(row["total_redeemed"]) if row.get("total_redeemed") is not None else None,
            total_coins_spent=int(row["total_coins_spent"]) if row.get("total_coins_spent") is not None else None,
            first_purchase_date=warehouse_value_to_utc_datetime(row.get("first_purchase_date")),
            last_purchase_date=warehouse_value_to_utc_datetime(row.get("last_purchase_date")),
            created_at=warehouse_value_to_utc_datetime(row.get("created_at")),
            stock_initial=int(row["stock_initial"]) if row.get("stock_initial") is not None else None,
            stock_total=int(row["stock_total"]) if row.get("stock_total") is not None else None,
            stock_remaining=int(row["stock_remaining"]) if row.get("stock_remaining") is not None else None,
        )
