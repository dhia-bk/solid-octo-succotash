"""
app/transformers/discussions.py
================================
Transformer for dim_discussions → Discussion nodes.

Emits Discussion nodes only.
JOINED_DISCUSSION (User → Discussion) is written by the discussion
events transformer, not here.
"""

from __future__ import annotations

from app.contracts.graph_records import GraphWriteBatch, NodeRecord
from app.contracts.warehouse_rows import ExtractorBatch
from app.core.constants import DISCUSSION
from app.core.exceptions import CanonicalizationError, TransformationError
from app.core.ids import build_discussion_id
from app.core.logging import log_transformation_finished, log_transformation_started
from app.schemas.warehouse.discussions import INCLUSION_MODE, SOURCE_NAME, DiscussionsRow
from app.transformers.base import BaseTransformer
from app.transformers.graph_record_builder import GraphRecordBuilder


class DiscussionsTransformer(BaseTransformer):
    """
    Transforms dim_discussions rows into Discussion nodes.

    Merge key strategy: direct on discussion_id (declared in merge_keys.py).
    Node id:           build_discussion_id(row.discussion_id)
    Relationships:     none — JOINED_DISCUSSION is written by discussion events.
    """

    source_name = SOURCE_NAME        # "dim_discussions"
    inclusion_mode = INCLUSION_MODE  # GRAPH_CORE

    def transform(self, batch: ExtractorBatch) -> GraphWriteBatch:
        self._reset_skip_count()
        builder = GraphRecordBuilder(self._run_id, SOURCE_NAME)
        nodes: list[NodeRecord] = []

        log_transformation_started(
            self._logger,
            table_name=SOURCE_NAME,
            run_id=self._run_id,
        )

        for row in batch.rows:
            row: DiscussionsRow
            try:
                nodes.append(self._transform_row(row, builder))
            except (TransformationError, CanonicalizationError) as exc:
                self._skip(str(exc), row_id=getattr(row, "discussion_id", None))
                continue

        log_transformation_finished(
            self._logger,
            record_count=len(nodes),
            table_name=SOURCE_NAME,
            run_id=self._run_id,
        )

        return builder.batch(nodes, [], batch_sequence=0)

    # -- Row-level transform --------------------------------------------------

    def _transform_row(
        self,
        row: DiscussionsRow,
        builder: GraphRecordBuilder,
    ) -> NodeRecord:
        if row.discussion_id is None:
            raise TransformationError(
                "DiscussionsRow missing required discussion_id",
                source=SOURCE_NAME,
            )

        node_id = build_discussion_id(row.discussion_id)

        properties = {
            "fixture_id":  row.fixture_id,
            "created_at":  self._ts(row.created_at_utc),
            "is_closed":   self._bool(row.is_closed),
        }

        return builder.node(DISCUSSION, node_id, properties)