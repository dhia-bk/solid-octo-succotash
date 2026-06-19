"""
app/transformers/duels.py
==========================
Transformer for fct_prediction_duels → Duel nodes + CHALLENGED relationships.

Emits:
    - Duel node (one per row)
    - CHALLENGED rel (sender_user → Duel) when sender_user_id is present

entry_fee is int | None on the row (not DECIMAL) — passed directly.
TINYINT: is_processed → self._bool()
"""

from __future__ import annotations

from app.contracts.graph_records import GraphWriteBatch, NodeRecord, RelationshipRecord
from app.contracts.warehouse_rows import ExtractorBatch
from app.core.constants import CHALLENGED, DUEL, USER
from app.core.exceptions import CanonicalizationError, TransformationError
from app.core.ids import build_duel_id, build_user_id
from app.core.logging import log_transformation_finished, log_transformation_started
from app.schemas.warehouse.prediction_duels import (
    INCLUSION_MODE,
    SOURCE_NAME,
    PredictionDuelsRow,
)
from app.transformers.base import BaseTransformer
from app.transformers.graph_record_builder import GraphRecordBuilder


class DuelsTransformer(BaseTransformer):
    """
    Transforms fct_prediction_duels rows into Duel nodes and CHALLENGED
    relationship records.

    Merge key strategy: direct on duel_id (declared in merge_keys.py).
    Node id: build_duel_id(row.duel_id)
    """

    source_name = SOURCE_NAME        # "fct_prediction_duels"
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
            row: PredictionDuelsRow
            try:
                node, challenged_rel = self._transform_row(row, builder)
                nodes.append(node)
                if challenged_rel is not None:
                    rels.append(challenged_rel)
            except (TransformationError, CanonicalizationError) as exc:
                self._skip(str(exc), row_id=getattr(row, "duel_id", None))
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
        row: PredictionDuelsRow,
        builder: GraphRecordBuilder,
    ) -> tuple[NodeRecord, RelationshipRecord | None]:
        if not row.duel_id:
            raise TransformationError(
                "PredictionDuelsRow missing required duel_id",
                source=SOURCE_NAME,
            )

        node_id = build_duel_id(row.duel_id)

        properties = {
            "fixture_id":            row.fixture_id,
            "sender_user_id":        row.sender_user_id,
            "receiver_user_id":      row.receiver_user_id,
            "entry_fee":             row.entry_fee,
            "status":                row.status,
            "winner_user_id":        row.winner_user_id,
            "is_processed":          self._bool(row.is_processed),
            "created_at":            self._ts(row.created_at_utc),
            "processed_at":          self._ts(row.processed_at_utc),
        }

        node = builder.node(DUEL, node_id, properties)

        challenged_rel = None
        if row.sender_user_id:
            challenged_rel = builder.rel(
                CHALLENGED,
                build_user_id(row.sender_user_id),
                node_id,
                start_label=USER,
                end_label=DUEL,
                properties={"entry_fee": row.entry_fee},
            )
        else:
            self._skip(
                "sender_user_id is None — skipping CHALLENGED rel",
                row_id=row.duel_id,
            )

        return node, challenged_rel