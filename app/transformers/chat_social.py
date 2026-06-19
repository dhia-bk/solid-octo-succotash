"""
app/transformers/chat_social.py
================================
Transformer for dim_chat_conversations_mysql + dim_chat_direct_pairs →
Conversation nodes, DirectPair nodes, and DIRECT_MESSAGE relationships.

Dispatches on batch.source_name:
    "dim_chat_conversations_mysql" → Conversation nodes
    "dim_chat_direct_pairs"        → DirectPair nodes + DIRECT_MESSAGE rels

DIRECT_MESSAGE rels are emitted from dim_chat_direct_pairs only —
one rel per participant (user_a and user_b both link to the DirectPair).
No endpoint spec is declared for DIRECT_MESSAGE — direct id construction.

Fields excluded from ConversationNode shape:
    conversation_name, last_message_at, created_at_utc,
    direct_pair_key, attachment_count, image_count

Fields excluded from DirectPairNode shape:
    conversation_count, attachment_count, image_count, created_at
"""

from __future__ import annotations

from app.contracts.graph_records import GraphWriteBatch, NodeRecord, RelationshipRecord
from app.contracts.warehouse_rows import ExtractorBatch
from app.core.constants import CONVERSATION, DIRECT_MESSAGE, DIRECT_PAIR, USER
from app.core.exceptions import CanonicalizationError, TransformationError
from app.core.ids import build_user_id, normalize_string_id
from app.core.logging import log_transformation_finished, log_transformation_started
from app.schemas.warehouse.chat_conversations import (
    INCLUSION_MODE as CONV_INCLUSION_MODE,
    SOURCE_NAME as CONV_SOURCE_NAME,
    ChatConversationsRow,
)
from app.schemas.warehouse.chat_direct_pairs import (
    SOURCE_NAME as PAIRS_SOURCE_NAME,
    ChatDirectPairsRow,
)
from app.transformers.base import BaseTransformer
from app.transformers.graph_record_builder import GraphRecordBuilder

_CONV_SOURCE = CONV_SOURCE_NAME    
_PAIRS_SOURCE = PAIRS_SOURCE_NAME  


class ChatSocialTransformer(BaseTransformer):
    """
    Transforms chat conversation and direct pair rows into graph records.

    Registered under dim_chat_conversations_mysql as the primary source.
    The pipeline must also route dim_chat_direct_pairs batches here.

    Merge key strategies:
        Conversation: direct on conversation_id
        DirectPair:   direct on direct_pair_key (order-normalized in DWH)
    """

    source_name = _CONV_SOURCE
    inclusion_mode = CONV_INCLUSION_MODE  # GRAPH_CORE

    def transform(self, batch: ExtractorBatch) -> GraphWriteBatch:
        if batch.source_name == _CONV_SOURCE:
            return self._transform_conversations(batch)
        if batch.source_name == _PAIRS_SOURCE:
            return self._transform_direct_pairs(batch)
        raise TransformationError(
            f"ChatSocialTransformer received unexpected source '{batch.source_name}'. "
            f"Expected '{_CONV_SOURCE}' or '{_PAIRS_SOURCE}'.",
            source=batch.source_name,
        )

    # -- Conversations --------------------------------------------------------

    def _transform_conversations(self, batch: ExtractorBatch) -> GraphWriteBatch:
        self._reset_skip_count()
        builder = GraphRecordBuilder(self._run_id, _CONV_SOURCE)
        nodes: list[NodeRecord] = []

        log_transformation_started(self._logger, table_name=_CONV_SOURCE, run_id=self._run_id)

        for row in batch.rows:
            row: ChatConversationsRow
            try:
                nodes.append(self._transform_conversation_row(row, builder))
            except (TransformationError, CanonicalizationError) as exc:
                self._skip(str(exc), row_id=getattr(row, "conversation_id", None))
                continue

        log_transformation_finished(self._logger, record_count=len(nodes), table_name=_CONV_SOURCE, run_id=self._run_id)
        return builder.batch(nodes, [], batch_sequence=0)

    def _transform_conversation_row(
        self,
        row: ChatConversationsRow,
        builder: GraphRecordBuilder,
    ) -> NodeRecord:
        if not row.conversation_id:
            raise TransformationError("ChatConversationsRow missing required conversation_id", source=_CONV_SOURCE)

        node_id = normalize_string_id(row.conversation_id)

        properties = {
            "conversation_type":    row.conversation_type,
            "private_league_id":    str(row.private_league_id) if row.private_league_id is not None else None,
            "created_by_user_id":   row.created_by_user_id,
            "is_active":            self._bool(row.is_active),
            "total_messages":       row.total_messages,
            "participant_count":    row.participant_count,
        }

        return builder.node(CONVERSATION, node_id, properties)

    # -- Direct pairs ---------------------------------------------------------

    def _transform_direct_pairs(self, batch: ExtractorBatch) -> GraphWriteBatch:
        self._reset_skip_count()
        builder = GraphRecordBuilder(self._run_id, _PAIRS_SOURCE)
        nodes: list[NodeRecord] = []
        rels: list[RelationshipRecord] = []

        log_transformation_started(self._logger, table_name=_PAIRS_SOURCE, run_id=self._run_id)

        for row in batch.rows:
            row: ChatDirectPairsRow
            try:
                node, row_rels = self._transform_direct_pair_row(row, builder)
                nodes.append(node)
                rels.extend(row_rels)
            except (TransformationError, CanonicalizationError) as exc:
                self._skip(str(exc), row_id=getattr(row, "direct_pair_key", None))
                continue

        log_transformation_finished(self._logger, record_count=len(nodes) + len(rels), table_name=_PAIRS_SOURCE, run_id=self._run_id)
        return builder.batch(nodes, rels, batch_sequence=0)

    def _transform_direct_pair_row(
        self,
        row: ChatDirectPairsRow,
        builder: GraphRecordBuilder,
    ) -> tuple[NodeRecord, list[RelationshipRecord]]:
        if not row.direct_pair_key:
            raise TransformationError("ChatDirectPairsRow missing required direct_pair_key", source=_PAIRS_SOURCE)

        node_id = normalize_string_id(row.direct_pair_key)

        properties = {
            "user_a_id":        row.user_a_id,
            "user_b_id":        row.user_b_id,
            "total_messages":   row.total_messages,
            "first_message_at": self._ts(row.first_message_at),
            "last_message_at":  self._ts(row.last_message_at),
        }

        node = builder.node(DIRECT_PAIR, node_id, properties)
        row_rels: list[RelationshipRecord] = []

        # Emit one DIRECT_MESSAGE rel per participant
        for user_id in (row.user_a_id, row.user_b_id):
            if not user_id:
                self._skip(
                    "user_id is None — skipping one DIRECT_MESSAGE rel",
                    row_id=row.direct_pair_key,
                )
                continue
            row_rels.append(
                builder.rel(
                    DIRECT_MESSAGE,
                    build_user_id(user_id),
                    node_id,
                    start_label=USER,
                    end_label=DIRECT_PAIR,
                )
            )

        return node, row_rels