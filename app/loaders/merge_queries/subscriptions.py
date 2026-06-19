"""
Merge queries for subscriptions.
Source(s): dim_subscription_products, fct_subscription_lifecycle
"""

from __future__ import annotations

from app.loaders.merge_queries.base import (
    build_node_merge_query,
    build_relationship_merge_query,
)


def get_subscription_product_merge_query(
    source_name: str = "dim_subscription_products",
) -> str:
    """Return Cypher MERGE query for SubscriptionProduct nodes."""
    return build_node_merge_query(
        label="SubscriptionProduct",
        merge_key_field="id",
        write_once_fields=[],
        mutable_fields=[
            "product_name",
            "price",
            "currency",
            "interval",
            "features",
            "is_active",
        ],
    )


def get_subscribed_to_merge_query(
    source_name: str = "fct_subscription_lifecycle",
) -> str:
    """Return Cypher MERGE query for SUBSCRIBED_TO relationships (User→SubscriptionProduct)."""
    return build_relationship_merge_query(
        rel_type="SUBSCRIBED_TO",
        start_label="User",
        end_label="SubscriptionProduct",
        start_merge_field="id",
        end_merge_field="id",
        rel_merge_fields=["lifecycle_event_id"],
        rel_property_fields=["subscribed_at", "expires_at", "status", "renewal_count"],
    )
