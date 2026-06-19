"""
app/transformers/notifications.py
===================================
Transformer for three notification sources → NotificationContent nodes,
RECEIVED_NOTIFICATION rels, and User notification preference enrichment.

Dispatches on batch.source_name:
    "dim_notification_content"      → NotificationContent nodes
    "jct_notification_recipients"   → RECEIVED_NOTIFICATION rels
    "dim_notification_preferences"  → User nodes (notification enrichment)

NotificationContent node id:
    Fallback strategy per merge_keys.py:
    build_notification_content_id(row.content_id) if not None,
    else build_notification_content_id(row.notification_id).

RECEIVED_NOTIFICATION end node id:
    Uses content_id from recipient row when present (matches NotificationContent
    node key), falls back to notification_id.

dim_notification_preferences note:
    One row per (user_id, subscription_category). This transformer writes
    the most recent preference state per user — no grouping needed since the
    loader's MERGE overwrites on each run.
"""

from __future__ import annotations

from app.contracts.graph_records import GraphWriteBatch, NodeRecord, RelationshipRecord
from app.contracts.warehouse_rows import ExtractorBatch
from app.core.constants import NOTIFICATION_CONTENT, RECEIVED_NOTIFICATION, USER
from app.core.exceptions import CanonicalizationError, TransformationError
from app.core.ids import build_notification_content_id, build_user_id
from app.core.logging import log_transformation_finished, log_transformation_started
from app.mappings.property_ownership import may_source_write_property
from app.schemas.warehouse.notification_content import (
    INCLUSION_MODE,
    SOURCE_NAME as CONTENT_SOURCE_NAME,
    NotificationContentRow,
)
from app.schemas.warehouse.notification_preferences import (
    SOURCE_NAME as PREFERENCES_SOURCE_NAME,
    NotificationPreferencesRow,
)
from app.schemas.warehouse.notification_recipients import (
    SOURCE_NAME as RECIPIENTS_SOURCE_NAME,
    NotificationRecipientsRow,
)
from app.transformers.base import BaseTransformer
from app.transformers.graph_record_builder import GraphRecordBuilder


class NotificationsTransformer(BaseTransformer):
    """
    Transforms notification sources into NotificationContent nodes,
    RECEIVED_NOTIFICATION relationship records, and User enrichment records.

    Registered under dim_notification_content as the primary source.
    """

    source_name = CONTENT_SOURCE_NAME   # "dim_notification_content"
    inclusion_mode = INCLUSION_MODE      # GRAPH_CORE

    def transform(self, batch: ExtractorBatch) -> GraphWriteBatch:
        if batch.source_name == CONTENT_SOURCE_NAME:
            return self._transform_content(batch)
        if batch.source_name == RECIPIENTS_SOURCE_NAME:
            return self._transform_recipients(batch)
        if batch.source_name == PREFERENCES_SOURCE_NAME:
            return self._transform_preferences(batch)
        raise TransformationError(
            f"NotificationsTransformer received unexpected source '{batch.source_name}'",
            source=batch.source_name,
        )

    # -- NotificationContent nodes --------------------------------------------

    def _transform_content(self, batch: ExtractorBatch) -> GraphWriteBatch:
        self._reset_skip_count()
        builder = GraphRecordBuilder(self._run_id, CONTENT_SOURCE_NAME)
        nodes: list[NodeRecord] = []

        log_transformation_started(self._logger, table_name=CONTENT_SOURCE_NAME, run_id=self._run_id)

        for row in batch.rows:
            row: NotificationContentRow
            try:
                if not row.content_id:
                    raise TransformationError("Missing content_id", source=CONTENT_SOURCE_NAME)

                node_id = build_notification_content_id(row.content_id)

                properties = {
                    "sender_user_id":          row.sender_user_id,
                    "normalized_message_text": row.normalized_message_text,
                    "message_text_sample":     row.message_text_sample,
                    "first_seen_at":           self._ts(row.first_seen_at_utc),
                    "last_seen_at":            self._ts(row.last_seen_at_utc),
                }

                nodes.append(builder.node(NOTIFICATION_CONTENT, node_id, properties))

            except (TransformationError, CanonicalizationError) as exc:
                self._skip(str(exc), row_id=getattr(row, "content_id", None))

        log_transformation_finished(self._logger, record_count=len(nodes), table_name=CONTENT_SOURCE_NAME, run_id=self._run_id)
        return builder.batch(nodes, [], batch_sequence=0)

    # -- RECEIVED_NOTIFICATION rels -------------------------------------------

    def _transform_recipients(self, batch: ExtractorBatch) -> GraphWriteBatch:
        self._reset_skip_count()
        builder = GraphRecordBuilder(self._run_id, RECIPIENTS_SOURCE_NAME)
        rels: list[RelationshipRecord] = []

        log_transformation_started(self._logger, table_name=RECIPIENTS_SOURCE_NAME, run_id=self._run_id)

        for row in batch.rows:
            row: NotificationRecipientsRow
            try:
                if not row.user_id:
                    self._skip("user_id is None — skipping RECEIVED_NOTIFICATION rel", row_id=row.notification_id)
                    continue

                # End node id: content_id preferred, notification_id fallback
                end_key = row.content_id or row.notification_id
                if not end_key:
                    self._skip("both content_id and notification_id are None — skipping RECEIVED_NOTIFICATION rel", row_id=row.notification_id)
                    continue

                content_node_id = build_notification_content_id(end_key)

                rels.append(builder.rel(
                    RECEIVED_NOTIFICATION,
                    build_user_id(row.user_id),
                    content_node_id,
                    start_label=USER,
                    end_label=NOTIFICATION_CONTENT,
                    properties={
                        "notification_id": row.notification_id,
                        "sent_at":         self._ts(row.sent_at_utc),
                        "is_read":         self._bool(row.is_read),
                        "read_at":         self._ts(row.read_at_utc),
                    },
                ))

            except (TransformationError, CanonicalizationError) as exc:
                self._skip(str(exc), row_id=getattr(row, "notification_id", None))

        log_transformation_finished(self._logger, record_count=len(rels), table_name=RECIPIENTS_SOURCE_NAME, run_id=self._run_id)
        return builder.batch([], rels, batch_sequence=0)

    # -- User notification preference enrichment ------------------------------

    def _transform_preferences(self, batch: ExtractorBatch) -> GraphWriteBatch:
        self._reset_skip_count()
        builder = GraphRecordBuilder(self._run_id, PREFERENCES_SOURCE_NAME)
        nodes: list[NodeRecord] = []

        log_transformation_started(self._logger, table_name=PREFERENCES_SOURCE_NAME, run_id=self._run_id)

        for row in batch.rows:
            row: NotificationPreferencesRow
            try:
                if not row.user_id:
                    raise TransformationError("Missing user_id", source=PREFERENCES_SOURCE_NAME)

                user_node_id = build_user_id(row.user_id)

                candidates = {
                    "registered_device_count": row.registered_device_count,
                    "device_platforms":        row.device_platforms,
                    "notification_enabled":    self._bool(row.is_enabled),
                }

                properties = {
                    k: v for k, v in candidates.items()
                    if may_source_write_property(PREFERENCES_SOURCE_NAME, "User", k)
                }

                nodes.append(builder.node(USER, user_node_id, properties))

            except (TransformationError, CanonicalizationError) as exc:
                self._skip(str(exc), row_id=getattr(row, "user_id", None))

        log_transformation_finished(self._logger, record_count=len(nodes), table_name=PREFERENCES_SOURCE_NAME, run_id=self._run_id)
        return builder.batch(nodes, [], batch_sequence=0)