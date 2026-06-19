"""
Warehouse schema for dim_subscription_products.

Source table: dim_subscription_products
Domain: economy
Inclusion mode: GRAPH_CORE — direct graph node creation
Graph entity: SubscriptionProduct
Freshness field: None (static dimension — full refresh on every run)

Subscription tier catalog. Changes infrequently; no timestamp column in DWH.
Feeds SubscriptionProduct nodes and SUBSCRIBED_TO relationship
(User → SubscriptionProduct).

DWH type notes:
    subscription_price — DECIMAL(10,2); float | None.
    All has_* fields   — TINYINT 0/1 permission flags.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.core.constants import GRAPH_CORE, SUBSCRIPTION_PRODUCT
from app.core.ids import normalize_string_id

# ── Module-level constants ────────────────────────────────────────────────────

SOURCE_NAME: str = "dim_subscription_products"
INCLUSION_MODE: str = GRAPH_CORE
PRIMARY_KEYS: tuple[str, ...] = ("subscription_type_id",)
FRESHNESS_FIELD: str | None = None
GRAPH_ENTITY_MAPPINGS: tuple[str, ...] = (SUBSCRIPTION_PRODUCT,)


# ── Row shape ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class SubscriptionProductsRow:
    """
    Typed row shape for dim_subscription_products.

    TINYINT fields (0/1 permission flags, not booleans in the DWH):
        has_early_prediction_permission
        has_predictive_algorithm_permission
        has_group_chat_create_permission
        has_private_chat_create_permission
        has_private_league_create_permission
        has_prediction_edit_permission

    subscription_price is DECIMAL(10,2) in the DWH; float | None.
    """

    subscription_type_id: int
    subscription_name: str | None
    subscription_price: float | None
    duration_in_days: int | None
    has_early_prediction_permission: int | None
    has_predictive_algorithm_permission: int | None
    has_group_chat_create_permission: int | None
    has_private_chat_create_permission: int | None
    has_private_league_create_permission: int | None
    has_prediction_edit_permission: int | None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> SubscriptionProductsRow:
        """Normalize a raw warehouse row into a typed SubscriptionProductsRow."""
        return cls(
            subscription_type_id=int(normalize_string_id(row["subscription_type_id"], field_name="subscription_type_id")),
            subscription_name=row.get("subscription_name"),
            subscription_price=float(row["subscription_price"]) if row.get("subscription_price") is not None else None,
            duration_in_days=int(row["duration_in_days"]) if row.get("duration_in_days") is not None else None,
            has_early_prediction_permission=int(row["has_early_prediction_permission"]) if row.get("has_early_prediction_permission") is not None else None,
            has_predictive_algorithm_permission=int(row["has_predictive_algorithm_permission"]) if row.get("has_predictive_algorithm_permission") is not None else None,
            has_group_chat_create_permission=int(row["has_group_chat_create_permission"]) if row.get("has_group_chat_create_permission") is not None else None,
            has_private_chat_create_permission=int(row["has_private_chat_create_permission"]) if row.get("has_private_chat_create_permission") is not None else None,
            has_private_league_create_permission=int(row["has_private_league_create_permission"]) if row.get("has_private_league_create_permission") is not None else None,
            has_prediction_edit_permission=int(row["has_prediction_edit_permission"]) if row.get("has_prediction_edit_permission") is not None else None,
        )
