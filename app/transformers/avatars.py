"""
app/transformers/avatars.py
============================
Transformer for dim_avatars → Avatar nodes.

Full-refresh source — no watermark, no incremental logic.
Emits Avatar nodes only. The EQUIPPED relationship (User → Avatar)
is written by the identity layer, not here.
"""

from __future__ import annotations

from app.contracts.graph_records import GraphWriteBatch, NodeRecord
from app.contracts.warehouse_rows import ExtractorBatch
from app.core.constants import AVATAR
from app.core.exceptions import CanonicalizationError, TransformationError
from app.core.ids import build_avatar_id
from app.core.logging import log_transformation_finished, log_transformation_started
from app.schemas.warehouse.avatars import INCLUSION_MODE, SOURCE_NAME, AvatarsRow
from app.transformers.base import BaseTransformer
from app.transformers.graph_record_builder import GraphRecordBuilder


class AvatarsTransformer(BaseTransformer):
    """
    Transforms dim_avatars rows into Avatar nodes.

    Merge key strategy: direct on avatar_id (declared in merge_keys.py).
    Node id:           build_avatar_id(row.avatar_id)
    Relationships:     none — EQUIPPED is written by the identity layer.
    """

    source_name = SOURCE_NAME       # "dim_avatars"
    inclusion_mode = INCLUSION_MODE  # GRAPH_CORE

    def transform(self, batch: ExtractorBatch) -> GraphWriteBatch:
        """
        Transform a batch of AvatarsRow instances into Avatar node records.

        Args:
            batch: ExtractorBatch from the dim_avatars extractor.

        Returns:
            GraphWriteBatch containing Avatar NodeRecord instances.
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
            row: AvatarsRow
            try:
                nodes.append(self._transform_row(row, builder))
            except (TransformationError, CanonicalizationError) as exc:
                self._skip(str(exc), row_id=getattr(row, "avatar_id", None))
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
        row: AvatarsRow,
        builder: GraphRecordBuilder,
    ) -> NodeRecord:
        """
        Transform a single AvatarsRow into an Avatar NodeRecord.

        Args:
            row:     Typed AvatarsRow instance.
            builder: GraphRecordBuilder pre-filled with run_id and source.

        Returns:
            Validated Avatar NodeRecord.

        Raises:
            TransformationError: If avatar_id is missing.
        """
        if row.avatar_id is None:
            raise TransformationError(
                "AvatarsRow missing required avatar_id",
                source=SOURCE_NAME,
            )

        node_id = build_avatar_id(row.avatar_id)

        properties = {
            "avatar_name":        row.avatar_name,
            "avatar_image":       row.avatar_image,
            "avatar_description": row.avatar_description,
            "users_unlocked":     row.users_unlocked,
            "adoption_rate":      row.adoption_rate,
        }

        return builder.node(AVATAR, node_id, properties)