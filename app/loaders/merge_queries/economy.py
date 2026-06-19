"""
Merge queries for economy (coin transactions and financial events).
Source(s): fct_coin_transactions, fct_financial_events
"""

from __future__ import annotations

from app.loaders.merge_queries.base import (
    build_node_merge_query,
    build_relationship_merge_query,
)


def get_coin_transaction_merge_query(source_name: str = "fct_coin_transactions") -> str:
    """Return Cypher MERGE query for CoinTransaction nodes."""
    return build_node_merge_query(
        label="CoinTransaction",
        merge_key_field="id",
        write_once_fields=[],
        mutable_fields=[
            "transaction_type",
            "coin_amount",
            "balance_after",
            "transaction_at",
            "reference_id",
            "reference_type",
        ],
    )


def get_financial_event_merge_query(source_name: str = "fct_financial_events") -> str:
    """Return Cypher MERGE query for FinancialEvent nodes."""
    return build_node_merge_query(
        label="FinancialEvent",
        merge_key_field="id",
        write_once_fields=[],
        mutable_fields=[
            "event_type",
            "amount",
            "currency",
            "provider",
            "status",
            "event_at",
            "reference_id",
        ],
    )


def get_spent_merge_query(source_name: str = "fct_coin_transactions") -> str:
    """Return Cypher MERGE query for SPENT relationships (User→CoinTransaction)."""
    return build_relationship_merge_query(
        rel_type="SPENT",
        start_label="User",
        end_label="CoinTransaction",
        start_merge_field="id",
        end_merge_field="id",
        rel_merge_fields=["event_id"],
        rel_property_fields=["transaction_at", "coin_amount"],
    )
