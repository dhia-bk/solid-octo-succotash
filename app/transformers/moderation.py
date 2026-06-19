"""
app/transformers/moderation.py
================================
Transformer for fct_moderation_events → ModerationEvent nodes + MODERATED rels.

Emits:
    - ModerationEvent node (one per row)
    - MODERATED rel (moderator_user → ModerationEvent) when moderator_user_id present

decision_confidence_score is DECIMAL on the row — written as float
(ModerationEventNode shape declares float | None).
automated_flag is TINYINT → self._bool().
"""

from __future__ import annotations

from app.contracts.graph_records import GraphWriteBatch, NodeRecord, RelationshipRecord
from app.contracts.warehouse_rows import ExtractorBatch
from app.core.constants import MODERATED, MODERATION_EVENT, USER
from app.core.exceptions import CanonicalizationError, TransformationError
from app.core.ids import build_moderation_event_id, build_user_id
from app.core.logging import log_transformation_finished, log_transformation_started
from app.schemas.warehouse.moderation_events import (
    INCLUSION_MODE,
    SOURCE_NAME,
    ModerationEventsRow,
)
from app.transformers.base import BaseTransformer
from app.transformers.graph_record_builder import GraphRecordBuilder


class ModerationTransformer(BaseTransformer):
    """
    Transforms fct_moderation_events rows into ModerationEvent nodes and
    MODERATED relationship records.

    Merge key strategy: direct on event_id.
    Node id: build_moderation_event_id(row.event_id)
    """

    source_name = SOURCE_NAME        # "fct_moderation_events"
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
            row: ModerationEventsRow
            try:
                node, moderated_rel = self._transform_row(row, builder)
                nodes.append(node)
                if moderated_rel is not None:
                    rels.append(moderated_rel)
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
        row: ModerationEventsRow,
        builder: GraphRecordBuilder,
    ) -> tuple[NodeRecord, RelationshipRecord | None]:
        if not row.event_id:
            raise TransformationError(
                "ModerationEventsRow missing required event_id",
                source=SOURCE_NAME,
            )

        node_id = build_moderation_event_id(row.event_id)

        properties = {
            "moderation_type":           row.moderation_type,
            "reason":                    row.reason,
            "status":                    row.status,
            "moderator_decision":        row.moderator_decision,
            "automated_flag":            self._bool(row.automated_flag),
            "decision_confidence_score": row.decision_confidence_score,
            "target_user_id":            row.target_user_id,
            "content_type":              row.content_type,
            "event_at":                  self._ts(row.event_at_utc),
        }

        node = builder.node(MODERATION_EVENT, node_id, properties)

        moderated_rel = None
        if row.moderator_user_id:
            moderated_rel = builder.rel(
                MODERATED,
                build_user_id(row.moderator_user_id),
                node_id,
                start_label=USER,
                end_label=MODERATION_EVENT,
            )
        else:
            self._skip(
                "moderator_user_id is None — skipping MODERATED rel",
                row_id=row.event_id,
            )

        return node, moderated_rel