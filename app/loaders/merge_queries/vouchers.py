"""
Merge queries for vouchers.
Source(s): dim_voucher_catalog, fct_voucher_purchases
"""

from __future__ import annotations

from app.loaders.merge_queries.base import (
    build_node_merge_query,
    build_relationship_merge_query,
)


def get_voucher_merge_query(source_name: str = "dim_voucher_catalog") -> str:
    """Return Cypher MERGE query for Voucher nodes."""
    return build_node_merge_query(
        label="Voucher",
        merge_key_field="id",
        write_once_fields=[],
        mutable_fields=[
            "voucher_name",
            "voucher_type",
            "coin_cost",
            "discount_value",
            "discount_type",
            "is_active",
            "expires_at",
        ],
    )


def get_purchased_merge_query(source_name: str = "fct_voucher_purchases") -> str:
    """Return Cypher MERGE query for PURCHASED relationships (User→Voucher)."""
    return build_relationship_merge_query(
        rel_type="PURCHASED",
        start_label="User",
        end_label="Voucher",
        start_merge_field="id",
        end_merge_field="id",
        rel_merge_fields=["purchase_id"],
        rel_property_fields=["purchased_at", "used_date", "status"],
    )
