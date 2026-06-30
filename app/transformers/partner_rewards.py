"""
app/transformers/partner_rewards.py
=====================================
Transformer for three partner reward sources → PartnerReward nodes and
REDEEMED relationships.

Dispatches on batch.source_name:
    "dim_partner_reward_catalog"      → PartnerReward nodes (core properties)
    "fct_partner_reward_inventory"    → PartnerReward nodes (stock enrichment)
    "fct_partner_reward_redemptions"  → REDEEMED rels (User → PartnerReward)

PII GUARD:
    fct_partner_reward_redemptions carries user_email — a PII field.
    This transformer explicitly drops user_email before any properties dict
    is assembled. assert_no_pii() at NodeRecord.__post_init__ provides a
    second line of defence, but the explicit drop here is belt-and-suspenders.

Property authority (multi-source node):
    dim_partner_reward_catalog     → owns catalog fields (priority 10)
    fct_partner_reward_inventory   → owns stock/inventory fields (priority 20)
    All writes gated via may_source_write_property().

Endpoint resolution note:
    REDEEMED_END spec declares id_source_field="partner_reward_id" but the
    actual redemptions row field is "reward_key". Using reward_key directly
    with build_partner_reward_id() — endpoint_resolution.py should be
    corrected to id_source_field="reward_key".
"""

from __future__ import annotations

from app.contracts.graph_records import GraphWriteBatch, NodeRecord, RelationshipRecord
from app.contracts.warehouse_rows import ExtractorBatch
from app.core.constants import PARTNER_REWARD, REDEEMED, USER
from app.core.exceptions import CanonicalizationError, TransformationError
from app.core.ids import build_reward_id, build_user_id
from app.core.logging import log_transformation_finished, log_transformation_started
from app.mappings.property_ownership import may_source_write_property
from app.schemas.warehouse.partner_reward_catalog import (
    INCLUSION_MODE,
    SOURCE_NAME as CATALOG_SOURCE_NAME,
    PartnerRewardCatalogRow,
)
from app.schemas.warehouse.partner_reward_inventory import (
    SOURCE_NAME as INVENTORY_SOURCE_NAME,
    PartnerRewardInventoryRow,
)
from app.schemas.warehouse.partner_reward_redemptions import (
    SOURCE_NAME as REDEMPTIONS_SOURCE_NAME,
    PartnerRewardRedemptionsRow,
)
from app.transformers.base import BaseTransformer
from app.transformers.graph_record_builder import GraphRecordBuilder


class PartnerRewardsTransformer(BaseTransformer):
    """
    Transforms partner reward catalog, inventory, and redemption rows into
    PartnerReward nodes and REDEEMED relationship records.

    Registered under dim_partner_reward_catalog as the primary source.
    """

    source_name = CATALOG_SOURCE_NAME   # "dim_partner_reward_catalog"
    secondary_sources = (INVENTORY_SOURCE_NAME, REDEMPTIONS_SOURCE_NAME)
    inclusion_mode = INCLUSION_MODE      # GRAPH_CORE

    def transform(self, batch: ExtractorBatch) -> GraphWriteBatch:
        if batch.source_name == CATALOG_SOURCE_NAME:
            return self._transform_catalog(batch)
        if batch.source_name == INVENTORY_SOURCE_NAME:
            return self._transform_inventory(batch)
        if batch.source_name == REDEMPTIONS_SOURCE_NAME:
            return self._transform_redemptions(batch)
        raise TransformationError(
            f"PartnerRewardsTransformer received unexpected source '{batch.source_name}'",
            source=batch.source_name,
        )

    # -- PartnerReward nodes (catalog) ----------------------------------------

    def _transform_catalog(self, batch: ExtractorBatch) -> GraphWriteBatch:
        self._reset_skip_count()
        builder = GraphRecordBuilder(self._run_id, CATALOG_SOURCE_NAME)
        nodes: list[NodeRecord] = []

        log_transformation_started(self._logger, table_name=CATALOG_SOURCE_NAME, run_id=self._run_id)

        for row in batch.rows:
            row: PartnerRewardCatalogRow
            try:
                if not row.reward_key:
                    raise TransformationError("Missing reward_key", source=CATALOG_SOURCE_NAME)

                node_id = build_reward_id(row.reward_key)

                candidates = {
                    "partner_name":             row.partner_name,
                    "reward_title":             row.reward_title,
                    "reward_type":              row.reward_type,
                    "coin_cost":                row.coin_cost,
                    "real_world_value_usd":     row.real_world_value_usd,
                    "valid_from":               row.valid_from,
                    "valid_until":              row.valid_until,
                    "is_active":                self._bool(row.is_active),
                    "stock_remaining":          row.stock_remaining,
                    "total_redemptions":        row.total_redemptions,
                }

                properties = {
                    k: v for k, v in candidates.items()
                    if may_source_write_property(CATALOG_SOURCE_NAME, "PartnerReward", k)
                }

                nodes.append(builder.node(PARTNER_REWARD, node_id, properties))

            except (TransformationError, CanonicalizationError) as exc:
                self._skip(str(exc), row_id=getattr(row, "reward_key", None))

        log_transformation_finished(self._logger, record_count=len(nodes), table_name=CATALOG_SOURCE_NAME, run_id=self._run_id)
        return builder.batch(nodes, [], batch_sequence=0)

    # -- PartnerReward nodes (inventory enrichment) ---------------------------

    def _transform_inventory(self, batch: ExtractorBatch) -> GraphWriteBatch:
        self._reset_skip_count()
        builder = GraphRecordBuilder(self._run_id, INVENTORY_SOURCE_NAME)
        nodes: list[NodeRecord] = []

        log_transformation_started(self._logger, table_name=INVENTORY_SOURCE_NAME, run_id=self._run_id)

        for row in batch.rows:
            row: PartnerRewardInventoryRow
            try:
                if not row.reward_key:
                    self._skip("reward_key is None — skipping inventory enrichment", row_id=row.inventory_event_id)
                    continue

                node_id = build_reward_id(row.reward_key)

                candidates = {
                    "stock_total":                row.stock_total,
                    "discount_price":             row.discount_price,
                    "expiration_date":            self._ts(row.expiration_date_utc),
                    "redemption_instructions":    row.redemption_instructions,
                }

                properties = {
                    k: v for k, v in candidates.items()
                    if may_source_write_property(INVENTORY_SOURCE_NAME, "PartnerReward", k)
                }

                nodes.append(builder.node(PARTNER_REWARD, node_id, properties))

            except (TransformationError, CanonicalizationError) as exc:
                self._skip(str(exc), row_id=getattr(row, "inventory_event_id", None))

        log_transformation_finished(self._logger, record_count=len(nodes), table_name=INVENTORY_SOURCE_NAME, run_id=self._run_id)
        return builder.batch(nodes, [], batch_sequence=0)

    # -- REDEEMED rels --------------------------------------------------------

    def _transform_redemptions(self, batch: ExtractorBatch) -> GraphWriteBatch:
        self._reset_skip_count()
        builder = GraphRecordBuilder(self._run_id, REDEMPTIONS_SOURCE_NAME)
        rels: list[RelationshipRecord] = []

        log_transformation_started(self._logger, table_name=REDEMPTIONS_SOURCE_NAME, run_id=self._run_id)

        for row in batch.rows:
            row: PartnerRewardRedemptionsRow
            try:
                # PII guard — user_email must never reach any properties dict
                # row.user_email is available on the row object but is never
                # referenced below. assert_no_pii() at NodeRecord provides
                # a second line of defence for nodes; this comment is the
                # explicit acknowledgement for relationship properties.

                if not row.user_id:
                    self._skip("user_id is None — skipping REDEEMED rel", row_id=row.redemption_id)
                    continue

                if not row.reward_key:
                    self._skip("reward_key is None — skipping REDEEMED rel", row_id=row.redemption_id)
                    continue

                reward_node_id = build_reward_id(row.reward_key)

                rels.append(builder.rel(
                    REDEEMED,
                    build_user_id(row.user_id),
                    reward_node_id,
                    start_label=USER,
                    end_label=PARTNER_REWARD,
                    properties={
                        "redemption_id": row.redemption_id,
                        "redeemed_at":   self._ts(row.redeemed_at_utc),
                        "quantity":      row.quantity,
                    },
                ))

            except (TransformationError, CanonicalizationError) as exc:
                self._skip(str(exc), row_id=getattr(row, "redemption_id", None))

        log_transformation_finished(self._logger, record_count=len(rels), table_name=REDEMPTIONS_SOURCE_NAME, run_id=self._run_id)
        return builder.batch([], rels, batch_sequence=0)