"""
Warehouse schema for fct_financials.

Source table: fct_financials
Domain: economy
Inclusion mode: GRAPH_CORE — direct graph node creation
Graph entity: FinancialEvent
Freshness field: event_at_utc

Payment and financial event log. Feeds FinancialEvent nodes linked to
User nodes via user_id.

DWH type notes:
    event_id     — VARCHAR(100) in DWH; str (spec suggested int).
    amount, mrr_change — DECIMAL(10,2); float | None.
    event_date_key — INTEGER partition key; str | None.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.core.constants import FINANCIAL_EVENT, GRAPH_CORE
from app.core.ids import normalize_nullable_string_id, normalize_string_id
from app.core.time import warehouse_value_to_utc_datetime

# ── Module-level constants ────────────────────────────────────────────────────

SOURCE_NAME: str = "fct_financials"
INCLUSION_MODE: str = GRAPH_CORE
PRIMARY_KEYS: tuple[str, ...] = ("event_id",)
FRESHNESS_FIELD: str | None = "event_at_utc"
GRAPH_ENTITY_MAPPINGS: tuple[str, ...] = (FINANCIAL_EVENT,)


# ── Row shape ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class FinancialsRow:
    """
    Typed row shape for fct_financials.

    event_id is VARCHAR(100) in the DWH; stored as str.
    amount and mrr_change are DECIMAL(10,2); float | None.
    event_date_key is an INTEGER partition key; str | None.
    """

    event_id: str
    amount: float | None
    currency: str | None
    event_at_utc: datetime | None
    event_date_key: str | None
    event_type: str | None
    mrr_change: float | None
    payment_method: str | None
    payment_status: str | None
    subscription_type_id: int | None
    transaction_id: str | None
    user_id: str | None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> FinancialsRow:
        """Normalize a raw warehouse row into a typed FinancialsRow."""
        return cls(
            event_id=normalize_string_id(row["event_id"], field_name="event_id"),
            amount=float(row["amount"]) if row.get("amount") is not None else None,
            currency=row.get("currency"),
            event_at_utc=warehouse_value_to_utc_datetime(row.get("event_at_utc")),
            event_date_key=str(row["event_date_key"]) if row.get("event_date_key") is not None else None,
            event_type=row.get("event_type"),
            mrr_change=float(row["mrr_change"]) if row.get("mrr_change") is not None else None,
            payment_method=row.get("payment_method"),
            payment_status=row.get("payment_status"),
            subscription_type_id=int(row["subscription_type_id"]) if row.get("subscription_type_id") is not None else None,
            transaction_id=normalize_nullable_string_id(row.get("transaction_id"), field_name="transaction_id"),
            user_id=normalize_nullable_string_id(row.get("user_id"), field_name="user_id"),
        )
