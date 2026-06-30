"""
app/transformers/economy.py
============================
Transformer for fct_coin_transactions → CoinTransaction nodes + SPENT rels.

Emits:
    - CoinTransaction node (one per row)
    - SPENT rel (User → CoinTransaction) when user_id is present

coin_amount and coin_balance_after are DECIMAL(18,4) on the row → self._int()
coercion per universal rules.

Note: merge_keys.py declares the merge field as "transaction_id" but the actual
row field is "event_id" — the node id is built from event_id. This discrepancy
in merge_keys.py should be corrected to "event_id".
"""

from __future__ import annotations

from app.contracts.graph_records import GraphWriteBatch, NodeRecord, RelationshipRecord
from app.contracts.warehouse_rows import ExtractorBatch
from app.core.constants import COIN_TRANSACTION, SPENT, USER
from app.core.exceptions import CanonicalizationError, TransformationError
from app.core.ids import build_user_id, normalize_string_id
from app.core.logging import log_transformation_finished, log_transformation_started
from app.schemas.warehouse.coin_transactions import (
    INCLUSION_MODE,
    SOURCE_NAME,
    CoinTransactionsRow,
)
from app.transformers.base import BaseTransformer
from app.transformers.graph_record_builder import GraphRecordBuilder


class EconomyTransformer(BaseTransformer):
    """
    Transforms fct_coin_transactions rows into CoinTransaction nodes and
    SPENT relationship records.

    Merge key strategy: direct on event_id.
    Node id: normalize_string_id(row.event_id)
    """

    source_name = SOURCE_NAME        # "fct_coin_transactions"
    inclusion_mode = INCLUSION_MODE  # GRAPH_CORE

    def transform(self, batch: ExtractorBatch) -> GraphWriteBatch:
        self._reset_skip_count()
        builder = GraphRecordBuilder(self._run_id, SOURCE_NAME)
        nodes: list[NodeRecord] = []
        rels: list[RelationshipRecord] = []

        log_transformation_started(
            self._logger,
            table_name=SOURCE_NAME,
            run_id=self._run_id,
        )

        for row in batch.rows:
            row: CoinTransactionsRow
            try:
                node, spent_rel = self._transform_row(row, builder)
                nodes.append(node)
                if spent_rel is not None:
                    rels.append(spent_rel)
            except (TransformationError, CanonicalizationError) as exc:
                self._skip(str(exc), row_id=getattr(row, "event_id", None))
                continue

        log_transformation_finished(
            self._logger,
            record_count=len(nodes) + len(rels),
            table_name=SOURCE_NAME,
            run_id=self._run_id,
        )

        return builder.batch(nodes, rels, batch_sequence=0)

    # -- Row-level transform --------------------------------------------------

    def _transform_row(
        self,
        row: CoinTransactionsRow,
        builder: GraphRecordBuilder,
    ) -> tuple[NodeRecord, RelationshipRecord | None]:
        if not row.event_id:
            raise TransformationError(
                "CoinTransactionsRow missing required event_id",
                source=SOURCE_NAME,
            )

        node_id = normalize_string_id(row.event_id)

        properties = {
            "transaction_type":   row.transaction_type,
            "event_type":         row.event_type,
            "coin_amount":        self._int(row.coin_amount),
            "coin_balance_after": self._int(row.coin_balance_after),
            "description":        row.description,
            "event_at":           self._ts(row.event_at_utc),
        }

        node = builder.node(COIN_TRANSACTION, node_id, properties)

        spent_rel = None
        if row.user_id:
            spent_rel = builder.rel(
                SPENT,
                build_user_id(row.user_id),
                node_id,
                start_label=USER,
                end_label=COIN_TRANSACTION,
                properties={
                    "event_id":    row.event_id,
                    "coin_amount": self._int(row.coin_amount),
                    "event_at":    self._ts(row.event_at_utc),
                },
            )
        else:
            self._skip(
                "user_id is None — skipping SPENT rel",
                row_id=row.event_id,
            )

        return node, spent_rel