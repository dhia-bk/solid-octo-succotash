"""
Economy pipeline — subscriptions, vouchers, partner rewards, coins, achievements.

Catalog nodes before their relationship sources throughout.
fct_partner_reward_redemptions carries PII — the transformer enforces the
PII pre-check before any properties reach the loader.
"""

from __future__ import annotations

from app.core.constants import ECONOMY_PIPELINE
from app.pipelines.base import BasePipeline


class EconomyPipeline(BasePipeline):
    """
    Loads economy domain: SubscriptionProduct, Voucher, PartnerReward,
    CoinTransaction, Achievement, and their user relationship edges.
    """

    pipeline_name = ECONOMY_PIPELINE
    sources = (
        "dim_subscription_products",        # SubscriptionProduct nodes
        "fct_subscription_lifecycle",       # SUBSCRIBED_TO rels
        "dim_voucher_catalog",              # Voucher nodes
        "fct_voucher_purchases",            # PURCHASED rels
        "dim_partner_reward_catalog",       # PartnerReward nodes (core)
        "fct_partner_reward_inventory",     # PartnerReward enrichment
        "fct_partner_reward_redemptions",   # REDEEMED rels — PII pre-check in transformer
"fct_awards_and_achievements",      # Achievement nodes + ACHIEVED rels
    )
