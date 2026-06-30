"""
app/transformers/subscriptions.py
===================================
Transformer for dim_subscription_products + fct_subscription_lifecycle →
SubscriptionProduct nodes + SUBSCRIBED_TO relationships.

Dispatches on batch.source_name:
    "dim_subscription_products"   → SubscriptionProduct nodes
    "fct_subscription_lifecycle"  → SUBSCRIBED_TO rels (User → SubscriptionProduct)
"""

from __future__ import annotations

from app.contracts.graph_records import GraphWriteBatch, NodeRecord, RelationshipRecord
from app.contracts.warehouse_rows import ExtractorBatch
from app.core.constants import SUBSCRIBED_TO, SUBSCRIPTION_PRODUCT, USER
from app.core.exceptions import CanonicalizationError, TransformationError
from app.core.ids import build_user_id, normalize_string_id
from app.core.logging import log_transformation_finished, log_transformation_started
from app.schemas.warehouse.subscription_lifecycle import (
    SOURCE_NAME as LIFECYCLE_SOURCE_NAME,
    SubscriptionLifecycleRow,
)
from app.schemas.warehouse.subscription_products import (
    INCLUSION_MODE,
    SOURCE_NAME as PRODUCTS_SOURCE_NAME,
    SubscriptionProductsRow,
)
from app.transformers.base import BaseTransformer
from app.transformers.graph_record_builder import GraphRecordBuilder


class SubscriptionsTransformer(BaseTransformer):
    """
    Transforms subscription product catalog and lifecycle rows into
    SubscriptionProduct nodes and SUBSCRIBED_TO relationship records.

    Registered under dim_subscription_products as the primary source.
    """

    source_name = PRODUCTS_SOURCE_NAME   # "dim_subscription_products"
    secondary_sources = (LIFECYCLE_SOURCE_NAME,)
    inclusion_mode = INCLUSION_MODE       # GRAPH_CORE

    def transform(self, batch: ExtractorBatch) -> GraphWriteBatch:
        if batch.source_name == PRODUCTS_SOURCE_NAME:
            return self._transform_products(batch)
        if batch.source_name == LIFECYCLE_SOURCE_NAME:
            return self._transform_lifecycle(batch)
        raise TransformationError(
            f"SubscriptionsTransformer received unexpected source '{batch.source_name}'",
            source=batch.source_name,
        )

    # -- SubscriptionProduct nodes --------------------------------------------

    def _transform_products(self, batch: ExtractorBatch) -> GraphWriteBatch:
        self._reset_skip_count()
        builder = GraphRecordBuilder(self._run_id, PRODUCTS_SOURCE_NAME)
        nodes: list[NodeRecord] = []

        log_transformation_started(self._logger, table_name=PRODUCTS_SOURCE_NAME, run_id=self._run_id)

        for row in batch.rows:
            row: SubscriptionProductsRow
            try:
                if row.subscription_type_id is None:
                    raise TransformationError("Missing subscription_type_id", source=PRODUCTS_SOURCE_NAME)

                node_id = normalize_string_id(row.subscription_type_id)

                properties = {
                    "subscription_name":  row.subscription_name,
                    "subscription_price": row.subscription_price,
                    "duration_in_days":   row.duration_in_days,
                    "has_early_prediction_permission":      self._bool(row.has_early_prediction_permission),
                    "has_predictive_algorithm_permission":  self._bool(row.has_predictive_algorithm_permission),
                    "has_group_chat_create_permission":     self._bool(row.has_group_chat_create_permission),
                    "has_private_chat_create_permission":   self._bool(row.has_private_chat_create_permission),
                    "has_private_league_create_permission": self._bool(row.has_private_league_create_permission),
                    "has_prediction_edit_permission":       self._bool(row.has_prediction_edit_permission),
                }

                nodes.append(builder.node(SUBSCRIPTION_PRODUCT, node_id, properties))

            except (TransformationError, CanonicalizationError) as exc:
                self._skip(str(exc), row_id=getattr(row, "subscription_type_id", None))

        log_transformation_finished(self._logger, record_count=len(nodes), table_name=PRODUCTS_SOURCE_NAME, run_id=self._run_id)
        return builder.batch(nodes, [], batch_sequence=0)

    # -- SUBSCRIBED_TO rels ---------------------------------------------------

    def _transform_lifecycle(self, batch: ExtractorBatch) -> GraphWriteBatch:
        self._reset_skip_count()
        builder = GraphRecordBuilder(self._run_id, LIFECYCLE_SOURCE_NAME)
        rels: list[RelationshipRecord] = []

        log_transformation_started(self._logger, table_name=LIFECYCLE_SOURCE_NAME, run_id=self._run_id)

        for row in batch.rows:
            row: SubscriptionLifecycleRow
            try:
                if not row.user_id:
                    self._skip("user_id is None — skipping SUBSCRIBED_TO rel", row_id=row.lifecycle_event_id)
                    continue

                if row.subscription_product_id is None:
                    self._skip("subscription_product_id is None — skipping SUBSCRIBED_TO rel", row_id=row.lifecycle_event_id)
                    continue

                product_node_id = normalize_string_id(row.subscription_product_id)

                rels.append(builder.rel(
                    SUBSCRIBED_TO,
                    build_user_id(row.user_id),
                    product_node_id,
                    start_label=USER,
                    end_label=SUBSCRIPTION_PRODUCT,
                    properties={
                        "lifecycle_event_id": row.lifecycle_event_id,
                        "event_type":         row.event_type,
                        "event_timestamp":    self._ts(row.event_timestamp_utc),
                        "amount_paid_usd":    row.amount_paid_usd,
                    },
                ))

            except (TransformationError, CanonicalizationError) as exc:
                self._skip(str(exc), row_id=getattr(row, "lifecycle_event_id", None))

        log_transformation_finished(self._logger, record_count=len(rels), table_name=LIFECYCLE_SOURCE_NAME, run_id=self._run_id)
        return builder.batch([], rels, batch_sequence=0)