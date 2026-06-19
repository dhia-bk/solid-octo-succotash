"""
Warehouse schema for fct_subscription_lifecycle.

Source table: fct_subscription_lifecycle
Domain: economy
Inclusion mode: GRAPH_CORE — feeds relationship creation
Graph entity: SUBSCRIBED_TO relationship (User → SubscriptionProduct)
Freshness field: event_timestamp_utc

Subscription lifecycle events (new, renewal, churn, win-back). No declared
PK constraint; lifecycle_event_id treated as the stable de facto key. Feeds
SUBSCRIBED_TO edge properties: event type, amount paid, churn risk.

DWH type notes:
    lifecycle_event_id — VARCHAR(50); no PK constraint; str.
    event_date_key     — INTEGER partition key; str | None.
    subscription_start_date, subscription_end_date — DATE columns;
        str | None (date-only; not converted to datetime).
    amount_paid_usd, lifetime_subscription_revenue_usd,
    churn_risk_score, mrr_renewal_delta, mrr_new_delta — DECIMAL; float | None.
    is_auto_renewal, is_win_back — TINYINT 0/1.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.core.constants import GRAPH_CORE, SUBSCRIBED_TO
from app.core.ids import normalize_nullable_string_id, normalize_string_id
from app.core.time import warehouse_value_to_utc_datetime

# ── Module-level constants ────────────────────────────────────────────────────

SOURCE_NAME: str = "fct_subscription_lifecycle"
INCLUSION_MODE: str = GRAPH_CORE
PRIMARY_KEYS: tuple[str, ...] = ("lifecycle_event_id",)
FRESHNESS_FIELD: str | None = "event_timestamp_utc"
GRAPH_ENTITY_MAPPINGS: tuple[str, ...] = (SUBSCRIBED_TO,)


# ── Row shape ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class SubscriptionLifecycleRow:
    """
    Typed row shape for fct_subscription_lifecycle.

    TINYINT fields (0/1 integers, not booleans in the DWH):
        is_auto_renewal
        is_win_back

    subscription_start_date and subscription_end_date are DATE columns;
    stored as str | None (date-only semantics; no timezone conversion).
    event_date_key is an INTEGER partition key; str | None.
    lifecycle_event_id has no PK constraint; treated as the stable de facto key.
    """

    lifecycle_event_id: str
    user_id: str | None
    subscription_product_id: int | None
    event_type: str | None
    event_timestamp_utc: datetime | None
    event_date_key: str | None
    subscription_start_date: str | None
    subscription_end_date: str | None
    previous_product_id: int | None
    billing_cycle: str | None
    amount_paid_usd: float | None
    payment_method: str | None
    cancellation_reason: str | None
    is_auto_renewal: int | None
    days_since_last_event: int | None
    lifetime_subscription_months: int | None
    lifetime_subscription_revenue_usd: float | None
    is_win_back: int | None
    churn_risk_score: float | None
    currency: str | None
    payment_intent_id: str | None
    payment_status: str | None
    mrr_renewal_delta: float | None
    mrr_new_delta: float | None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> SubscriptionLifecycleRow:
        """Normalize a raw warehouse row into a typed SubscriptionLifecycleRow."""
        return cls(
            lifecycle_event_id=normalize_string_id(row["lifecycle_event_id"], field_name="lifecycle_event_id"),
            user_id=normalize_nullable_string_id(row.get("user_id"), field_name="user_id"),
            subscription_product_id=int(row["subscription_product_id"]) if row.get("subscription_product_id") is not None else None,
            event_type=row.get("event_type"),
            event_timestamp_utc=warehouse_value_to_utc_datetime(row.get("event_timestamp_utc")),
            event_date_key=str(row["event_date_key"]) if row.get("event_date_key") is not None else None,
            subscription_start_date=str(row["subscription_start_date"]) if row.get("subscription_start_date") is not None else None,
            subscription_end_date=str(row["subscription_end_date"]) if row.get("subscription_end_date") is not None else None,
            previous_product_id=int(row["previous_product_id"]) if row.get("previous_product_id") is not None else None,
            billing_cycle=row.get("billing_cycle"),
            amount_paid_usd=float(row["amount_paid_usd"]) if row.get("amount_paid_usd") is not None else None,
            payment_method=row.get("payment_method"),
            cancellation_reason=row.get("cancellation_reason"),
            is_auto_renewal=int(row["is_auto_renewal"]) if row.get("is_auto_renewal") is not None else None,
            days_since_last_event=int(row["days_since_last_event"]) if row.get("days_since_last_event") is not None else None,
            lifetime_subscription_months=int(row["lifetime_subscription_months"]) if row.get("lifetime_subscription_months") is not None else None,
            lifetime_subscription_revenue_usd=float(row["lifetime_subscription_revenue_usd"]) if row.get("lifetime_subscription_revenue_usd") is not None else None,
            is_win_back=int(row["is_win_back"]) if row.get("is_win_back") is not None else None,
            churn_risk_score=float(row["churn_risk_score"]) if row.get("churn_risk_score") is not None else None,
            currency=row.get("currency"),
            payment_intent_id=normalize_nullable_string_id(row.get("payment_intent_id"), field_name="payment_intent_id"),
            payment_status=row.get("payment_status"),
            mrr_renewal_delta=float(row["mrr_renewal_delta"]) if row.get("mrr_renewal_delta") is not None else None,
            mrr_new_delta=float(row["mrr_new_delta"]) if row.get("mrr_new_delta") is not None else None,
        )
