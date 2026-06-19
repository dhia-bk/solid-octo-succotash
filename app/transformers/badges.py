"""
app/transformers/badges.py
===========================
Transformer for dim_badges → Badge nodes.

Full-refresh source — no watermark, no incremental logic.
Emits Badge nodes only. The AWARDED relationship (User → Badge)
is written by the achievements layer, not here.
"""

from __future__ import annotations

from app.contracts.graph_records import GraphWriteBatch, NodeRecord
from app.contracts.warehouse_rows import ExtractorBatch
from app.core.constants import BADGE
from app.core.exceptions import CanonicalizationError, TransformationError
from app.core.ids import build_badge_id
from app.core.logging import log_transformation_finished, log_transformation_started
from app.schemas.warehouse.badges import INCLUSION_MODE, SOURCE_NAME, BadgesRow
from app.transformers.base import BaseTransformer
from app.transformers.graph_record_builder import GraphRecordBuilder


class BadgesTransformer(BaseTransformer):
    """
    Transforms dim_badges rows into Badge nodes.

    Merge key strategy: direct on badge_id (declared in merge_keys.py).
    Node id:           build_badge_id(row.badge_id)
    Relationships:     none — AWARDED is written by the achievements layer.
    """

    source_name = SOURCE_NAME        # "dim_badges"
    inclusion_mode = INCLUSION_MODE  # GRAPH_CORE

    def transform(self, batch: ExtractorBatch) -> GraphWriteBatch:
        """
        Transform a batch of BadgesRow instances into Badge node records.

        Args:
            batch: ExtractorBatch from the dim_badges extractor.

        Returns:
            GraphWriteBatch containing Badge NodeRecord instances.
        """
        self._reset_skip_count()
        builder = GraphRecordBuilder(self._run_id, SOURCE_NAME)
        nodes: list[NodeRecord] = []

        log_transformation_started(
            self._logger,
            table_name=SOURCE_NAME,
            run_id=self._run_id,
        )

        for row in batch.rows:
            row: BadgesRow
            try:
                nodes.append(self._transform_row(row, builder))
            except (TransformationError, CanonicalizationError) as exc:
                self._skip(str(exc), row_id=getattr(row, "badge_id", None))
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
        row: BadgesRow,
        builder: GraphRecordBuilder,
    ) -> NodeRecord:
        """
        Transform a single BadgesRow into a Badge NodeRecord.

        Args:
            row:     Typed BadgesRow instance.
            builder: GraphRecordBuilder pre-filled with run_id and source.

        Returns:
            Validated Badge NodeRecord.

        Raises:
            TransformationError: If badge_id is missing.
        """
        if row.badge_id is None:
            raise TransformationError(
                "BadgesRow missing required badge_id",
                source=SOURCE_NAME,
            )

        node_id = build_badge_id(row.badge_id)

        properties = {
            "badge_name":        row.badge_name,
            "badge_image":       row.badge_image,
            "badge_description": row.badge_description,
            "users_awarded":     row.users_awarded,
            "adoption_rate":     row.adoption_rate,
        }

        return builder.node(BADGE, node_id, properties)