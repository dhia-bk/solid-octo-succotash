"""
app/transformers/rating_history.py
====================================
Transformer for fct_user_rating_history → RatingSnapshot nodes +
HAS_RATING relationships.

Emits:
    - RatingSnapshot node (one per row)
    - HAS_RATING rel (User → RatingSnapshot) when user_id is present

Fields excluded from RatingSnapshotNode shape:
    rating_date_key
"""

from __future__ import annotations

from app.contracts.graph_records import GraphWriteBatch, NodeRecord, RelationshipRecord
from app.contracts.warehouse_rows import ExtractorBatch
from app.core.constants import HAS_RATING, RATING_SNAPSHOT, USER
from app.core.exceptions import CanonicalizationError, TransformationError
from app.core.ids import build_user_id, normalize_string_id
from app.core.logging import log_transformation_finished, log_transformation_started
from app.schemas.warehouse.user_rating_history import (
    INCLUSION_MODE,
    SOURCE_NAME,
    UserRatingHistoryRow,
)
from app.transformers.base import BaseTransformer
from app.transformers.graph_record_builder import GraphRecordBuilder


class RatingHistoryTransformer(BaseTransformer):
    """
    Transforms fct_user_rating_history rows into RatingSnapshot nodes and
    HAS_RATING relationship records.

    Merge key strategy: direct on rating_event_id.
    Node id: normalize_string_id(row.rating_event_id)
    """

    source_name = SOURCE_NAME        # "fct_user_rating_history"
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
            row: UserRatingHistoryRow
            try:
                node, has_rating_rel = self._transform_row(row, builder)
                nodes.append(node)
                if has_rating_rel is not None:
                    rels.append(has_rating_rel)
            except (TransformationError, CanonicalizationError) as exc:
                self._skip(str(exc), row_id=getattr(row, "rating_event_id", None))
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
        row: UserRatingHistoryRow,
        builder: GraphRecordBuilder,
    ) -> tuple[NodeRecord, RelationshipRecord | None]:
        if not row.rating_event_id:
            raise TransformationError(
                "UserRatingHistoryRow missing required rating_event_id",
                source=SOURCE_NAME,
            )

        node_id = normalize_string_id(row.rating_event_id)

        properties = {
            "user_id":         row.user_id,
            "duel_id":         row.duel_id,
            "previous_rating": row.previous_rating,
            "new_rating":      row.new_rating,
            "change_amount":   row.change_amount,
            "reason":          row.reason,
            "created_at":      self._ts(row.created_at_utc),
        }

        node = builder.node(RATING_SNAPSHOT, node_id, properties)

        has_rating_rel = None
        if row.user_id:
            has_rating_rel = builder.rel(
                HAS_RATING,
                build_user_id(row.user_id),
                node_id,
                start_label=USER,
                end_label=RATING_SNAPSHOT,
            )
        else:
            self._skip(
                "user_id is None — skipping HAS_RATING rel",
                row_id=row.rating_event_id,
            )

        return node, has_rating_rel