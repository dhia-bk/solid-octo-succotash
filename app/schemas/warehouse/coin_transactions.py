"""
Warehouse schema for fct_coin_transactions.

Source table: fct_coin_transactions
Domain: economy
Inclusion mode: GRAPH_CORE — direct graph node creation
Graph entity: CoinTransaction
Freshness field: event_at_utc

Coin earn/spend event log. Feeds CoinTransaction nodes and the SPENT
relationship (User → CoinTransaction).

DWH type notes:
    event_id            — VARCHAR(100) in DWH; str (spec suggested int).
    coin_amount         — DECIMAL(18,4); float | None (spec suggested int).
    coin_balance_after  — DECIMAL(18,4); float | None (spec suggested int).
    event_date_key      — INTEGER partition key; str | None.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.core.constants import COIN_TRANSACTION, GRAPH_CORE
from app.core.ids import normalize_nullable_string_id, normalize_string_id
from app.core.time import warehouse_value_to_utc_datetime

# ── Module-level constants ────────────────────────────────────────────────────

SOURCE_NAME: str = "fct_coin_transactions"
INCLUSION_MODE: str = GRAPH_CORE
PRIMARY_KEYS: tuple[str, ...] = ("event_id",)
FRESHNESS_FIELD: str | None = "event_at_utc"
GRAPH_ENTITY_MAPPINGS: tuple[str, ...] = (COIN_TRANSACTION,)


# ── Row shape ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class CoinTransactionsRow:
    """
    Typed row shape for fct_coin_transactions.

    event_id is VARCHAR(100) in the DWH; stored as str.
    coin_amount and coin_balance_after are DECIMAL(18,4); float | None.
    event_date_key is an INTEGER partition key; str | None.
    """

    event_id: str
    user_id: str | None
    transaction_type: str | None
    event_type: str | None
    primary_id: str | None
    secondary_id: str | None
    coin_amount: float | None
    coin_balance_after: float | None
    description: str | None
    event_at_utc: datetime | None
    event_date_key: str | None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> CoinTransactionsRow:
        """Normalize a raw warehouse row into a typed CoinTransactionsRow."""
        return cls(
            event_id=normalize_string_id(row["event_id"], field_name="event_id"),
            user_id=normalize_nullable_string_id(row.get("user_id"), field_name="user_id"),
            transaction_type=row.get("transaction_type"),
            event_type=row.get("event_type"),
            primary_id=normalize_nullable_string_id(row.get("primary_id"), field_name="primary_id"),
            secondary_id=normalize_nullable_string_id(row.get("secondary_id"), field_name="secondary_id"),
            coin_amount=float(row["coin_amount"]) if row.get("coin_amount") is not None else None,
            coin_balance_after=float(row["coin_balance_after"]) if row.get("coin_balance_after") is not None else None,
            description=row.get("description"),
            event_at_utc=warehouse_value_to_utc_datetime(row.get("event_at_utc")),
            event_date_key=str(row["event_date_key"]) if row.get("event_date_key") is not None else None,
        )
