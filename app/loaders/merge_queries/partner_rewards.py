"""
Merge queries for partner rewards.
Source(s): dim_partner_reward_catalog, fct_partner_reward_inventory, fct_partner_reward_redemptions
"""

from __future__ import annotations

from app.loaders.merge_queries.base import (
    build_enrichment_merge_query,
    build_node_merge_query,
    build_relationship_merge_query,
)


def get_partner_reward_merge_query(
    source_name: str = "dim_partner_reward_catalog",
) -> str:
    """Return Cypher MERGE query for PartnerReward nodes."""
    return build_node_merge_query(
        label="PartnerReward",
        merge_key_field="id",
        write_once_fields=["partner_name", "reward_name"],
        mutable_fields=["coin_cost", "is_active"],
    )


def get_partner_reward_enrichment_merge_query(
    source_name: str = "fct_partner_reward_inventory",
) -> str:
    """Return Cypher enrichment query writing inventory stats to PartnerReward nodes."""
    return build_enrichment_merge_query(
        label="PartnerReward",
        merge_key_field="id",
        enrichment_fields=[],
        write_policy_overwrite=["stock_total", "stock_remaining", "last_inventory_at"],
        write_policy_fill_if_null=[],
    )


def get_redeemed_merge_query(
    source_name: str = "fct_partner_reward_redemptions",
) -> str:
    """Return Cypher MERGE query for REDEEMED relationships (User→PartnerReward)."""
    return build_relationship_merge_query(
        rel_type="REDEEMED",
        start_label="User",
        end_label="PartnerReward",
        start_merge_field="id",
        end_merge_field="id",
        rel_merge_fields=["redemption_id"],
        rel_property_fields=["redeemed_at", "status", "coin_cost_at_redemption"],
    )
