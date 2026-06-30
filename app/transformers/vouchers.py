"""
app/transformers/vouchers.py
=============================
Transformer for dim_voucher_catalog + fct_voucher_purchases → Voucher nodes
+ PURCHASED relationships.

Dispatches on batch.source_name:
    "dim_voucher_catalog"   → Voucher nodes
    "fct_voucher_purchases" → PURCHASED rels (User → Voucher)

PURCHASED end endpoint uses VoucherCanonicalizer.resolve_purchase_voucher_id
via _resolve_endpoint() — declared in ENDPOINT_SPECS as PURCHASED_END.
VoucherCanonicalizer must be injected via canonicalizer_registry["vouchers"].
"""

from __future__ import annotations

from app.contracts.graph_records import GraphWriteBatch, NodeRecord, RelationshipRecord
from app.contracts.warehouse_rows import ExtractorBatch
from app.core.constants import PURCHASED, USER, VOUCHER
from app.core.exceptions import CanonicalizationError, TransformationError
from app.core.ids import build_user_id, build_voucher_id
from app.core.logging import log_transformation_finished, log_transformation_started
from app.schemas.warehouse.voucher_catalog import (
    INCLUSION_MODE,
    SOURCE_NAME as CATALOG_SOURCE_NAME,
    VoucherCatalogRow,
)
from app.schemas.warehouse.voucher_purchases import (
    SOURCE_NAME as PURCHASES_SOURCE_NAME,
    VoucherPurchasesRow,
)
from app.transformers.base import BaseTransformer
from app.transformers.graph_record_builder import GraphRecordBuilder


class VouchersTransformer(BaseTransformer):
    """
    Transforms voucher catalog and purchase rows into Voucher nodes and
    PURCHASED relationship records.

    Registered under dim_voucher_catalog as the primary source.

    Required injection: canonicalizer_registry["vouchers"] must contain a
    VoucherCanonicalizer with resolve_purchase_voucher_id method for
    PURCHASED end endpoint resolution.
    """

    source_name = CATALOG_SOURCE_NAME   # "dim_voucher_catalog"
    secondary_sources = (PURCHASES_SOURCE_NAME,)
    inclusion_mode = INCLUSION_MODE      # GRAPH_CORE

    def transform(self, batch: ExtractorBatch) -> GraphWriteBatch:
        if batch.source_name == CATALOG_SOURCE_NAME:
            return self._transform_catalog(batch)
        if batch.source_name == PURCHASES_SOURCE_NAME:
            return self._transform_purchases(batch)
        raise TransformationError(
            f"VouchersTransformer received unexpected source '{batch.source_name}'",
            source=batch.source_name,
        )

    # -- Voucher nodes --------------------------------------------------------

    def _transform_catalog(self, batch: ExtractorBatch) -> GraphWriteBatch:
        self._reset_skip_count()
        builder = GraphRecordBuilder(self._run_id, CATALOG_SOURCE_NAME)
        nodes: list[NodeRecord] = []

        log_transformation_started(self._logger, table_name=CATALOG_SOURCE_NAME, run_id=self._run_id)

        for row in batch.rows:
            row: VoucherCatalogRow
            try:
                if not row.voucher_key:
                    raise TransformationError("Missing voucher_key", source=CATALOG_SOURCE_NAME)

                node_id = build_voucher_id(row.voucher_key)

                properties = {
                    "voucher_title":       row.voucher_title,
                    "advertiser_name":     row.advertiser_name,
                    "acquisition_type":    row.acquisition_type,
                    "coin_cost":           row.coin_cost,
                    "expiry_date":         self._ts(row.expiry_date_utc),
                    "is_active":           self._bool(row.is_active),
                    "is_exclusive":        self._bool(row.is_exclusive),
                    "stock_remaining":     row.stock_remaining,
                    "total_purchases":     row.total_purchases,
                }

                nodes.append(builder.node(VOUCHER, node_id, properties))

            except (TransformationError, CanonicalizationError) as exc:
                self._skip(str(exc), row_id=getattr(row, "voucher_key", None))

        log_transformation_finished(self._logger, record_count=len(nodes), table_name=CATALOG_SOURCE_NAME, run_id=self._run_id)
        return builder.batch(nodes, [], batch_sequence=0)

    # -- PURCHASED rels -------------------------------------------------------

    def _transform_purchases(self, batch: ExtractorBatch) -> GraphWriteBatch:
        self._reset_skip_count()
        builder = GraphRecordBuilder(self._run_id, PURCHASES_SOURCE_NAME)
        rels: list[RelationshipRecord] = []

        log_transformation_started(self._logger, table_name=PURCHASES_SOURCE_NAME, run_id=self._run_id)

        for row in batch.rows:
            row: VoucherPurchasesRow
            try:
                if not row.user_id:
                    self._skip("user_id is None — skipping PURCHASED rel", row_id=row.purchase_id)
                    continue

                if not row.voucher_key:
                    self._skip("voucher_key is None — skipping PURCHASED rel", row_id=row.purchase_id)
                    continue

                # End endpoint via VoucherCanonicalizer.resolve_purchase_voucher_id
                try:
                    voucher_node_id = self._resolve_endpoint(PURCHASED, "end", row.voucher_key, source_name=PURCHASES_SOURCE_NAME)
                except TransformationError as exc:
                    self._skip(str(exc), row_id=row.purchase_id, voucher_key=row.voucher_key)
                    continue

                if voucher_node_id is None:
                    continue

                rels.append(builder.rel(
                    PURCHASED,
                    build_user_id(row.user_id),
                    voucher_node_id,
                    start_label=USER,
                    end_label=VOUCHER,
                    properties={
                        "purchase_id":   row.purchase_id,
                        "coin_cost":     row.coin_cost,
                        "purchase_date": self._ts(row.purchase_date_utc),
                    },
                ))

            except (TransformationError, CanonicalizationError) as exc:
                self._skip(str(exc), row_id=getattr(row, "purchase_id", None))

        log_transformation_finished(self._logger, record_count=len(rels), table_name=PURCHASES_SOURCE_NAME, run_id=self._run_id)
        return builder.batch([], rels, batch_sequence=0)