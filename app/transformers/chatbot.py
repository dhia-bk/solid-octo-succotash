"""
app/transformers/chatbot.py
============================
Transformer for three chatbot sources → ChatbotConversation, ChatbotMessage,
ToolCall, and Tool nodes plus TALKED_TO, HAS_MESSAGE, and USED_TOOL rels.

Dispatches on batch.source_name:
    "dim_chatbot_conversations" → ChatbotConversation nodes
                                  + TALKED_TO (User → ChatbotConversation)
    "fct_chatbot_messages"      → ChatbotMessage nodes
                                  + HAS_MESSAGE (ChatbotConversation → ChatbotMessage)
    "fct_chatbot_tool_calls"    → ToolCall nodes + Tool nodes (canonical)
                                  + USED_TOOL (ChatbotMessage → ToolCall)

Tool nodes:
    Canonical deduplicated nodes keyed by slugify(tool_name). Represent the
    tool type, not a single invocation. Emitted once per unique tool_name
    seen in the batch. USED_TOOL points to ToolCall (the invocation), not
    to Tool — Tool nodes are emitted for analytics queryability only.

No endpoint specs are declared for TALKED_TO, HAS_MESSAGE, or USED_TOOL —
all endpoints are direct id construction.
"""

from __future__ import annotations

from app.contracts.graph_records import GraphWriteBatch, NodeRecord, RelationshipRecord
from app.contracts.warehouse_rows import ExtractorBatch
from app.core.constants import (
    CHATBOT_CONVERSATION,
    CHATBOT_MESSAGE,
    HAS_MESSAGE,
    TALKED_TO,
    TOOL,
    TOOL_CALL,
    USED_TOOL,
    USER,
)
from app.core.exceptions import CanonicalizationError, TransformationError
from app.core.ids import (
    build_chatbot_conversation_id,
    build_chatbot_message_id,
    build_tool_call_id,
    build_user_id,
    slugify,
)
from app.core.logging import log_transformation_finished, log_transformation_started
from app.schemas.warehouse.chatbot_conversations import (
    INCLUSION_MODE,
    SOURCE_NAME as CONV_SOURCE_NAME,
    ChatbotConversationsRow,
)
from app.schemas.warehouse.chatbot_messages import (
    SOURCE_NAME as MSG_SOURCE_NAME,
    ChatbotMessagesRow,
)
from app.schemas.warehouse.chatbot_tool_calls import (
    SOURCE_NAME as TOOL_SOURCE_NAME,
    ChatbotToolCallsRow,
)
from app.transformers.base import BaseTransformer
from app.transformers.graph_record_builder import GraphRecordBuilder


class ChatbotTransformer(BaseTransformer):
    """
    Transforms three chatbot sources into chatbot graph records.

    Registered under dim_chatbot_conversations as the primary source.
    The pipeline must route all three chatbot sources here.
    """

    source_name = CONV_SOURCE_NAME   # "dim_chatbot_conversations"
    secondary_sources = (MSG_SOURCE_NAME, TOOL_SOURCE_NAME)
    inclusion_mode = INCLUSION_MODE  # GRAPH_CORE

    def transform(self, batch: ExtractorBatch) -> GraphWriteBatch:
        if batch.source_name == CONV_SOURCE_NAME:
            return self._transform_conversations(batch)
        if batch.source_name == MSG_SOURCE_NAME:
            return self._transform_messages(batch)
        if batch.source_name == TOOL_SOURCE_NAME:
            return self._transform_tool_calls(batch)
        raise TransformationError(
            f"ChatbotTransformer received unexpected source '{batch.source_name}'",
            source=batch.source_name,
        )

    # -- ChatbotConversation nodes + TALKED_TO rels ---------------------------

    def _transform_conversations(self, batch: ExtractorBatch) -> GraphWriteBatch:
        self._reset_skip_count()
        builder = GraphRecordBuilder(self._run_id, CONV_SOURCE_NAME)
        nodes: list[NodeRecord] = []
        rels: list[RelationshipRecord] = []

        log_transformation_started(self._logger, table_name=CONV_SOURCE_NAME, run_id=self._run_id)

        for row in batch.rows:
            row: ChatbotConversationsRow
            try:
                if not row.conversation_id:
                    raise TransformationError("Missing conversation_id", source=CONV_SOURCE_NAME)

                node_id = build_chatbot_conversation_id(row.conversation_id)

                properties = {
                    "source":                        row.source,
                    "conversation_start":             self._ts(row.conversation_start_utc),
                    "conversation_end":               self._ts(row.conversation_end_utc),
                    "duration_seconds":               row.duration_seconds,
                    "total_messages":                 row.total_messages,
                    "total_tool_calls":               row.total_tool_calls,
                    "total_tokens":                   row.total_tokens,
                    "model_family":                   row.model_family,
                    "conversation_length_category":   row.conversation_length_category,
                }

                nodes.append(builder.node(CHATBOT_CONVERSATION, node_id, properties))

                if row.user_id:
                    rels.append(builder.rel(
                        TALKED_TO,
                        build_user_id(row.user_id),
                        node_id,
                        start_label=USER,
                        end_label=CHATBOT_CONVERSATION,
                        properties={"conversation_start": self._ts(row.conversation_start_utc)},
                    ))
                else:
                    self._skip("user_id is None — skipping TALKED_TO rel", row_id=row.conversation_id)

            except (TransformationError, CanonicalizationError) as exc:
                self._skip(str(exc), row_id=getattr(row, "conversation_id", None))

        log_transformation_finished(self._logger, record_count=len(nodes) + len(rels), table_name=CONV_SOURCE_NAME, run_id=self._run_id)
        return builder.batch(nodes, rels, batch_sequence=0)

    # -- ChatbotMessage nodes + HAS_MESSAGE rels ------------------------------

    def _transform_messages(self, batch: ExtractorBatch) -> GraphWriteBatch:
        self._reset_skip_count()
        builder = GraphRecordBuilder(self._run_id, MSG_SOURCE_NAME)
        nodes: list[NodeRecord] = []
        rels: list[RelationshipRecord] = []

        log_transformation_started(self._logger, table_name=MSG_SOURCE_NAME, run_id=self._run_id)

        for row in batch.rows:
            row: ChatbotMessagesRow
            try:
                if not row.message_id:
                    raise TransformationError("Missing message_id", source=MSG_SOURCE_NAME)

                node_id = build_chatbot_message_id(row.message_id)

                properties = {
                    "message_type":       row.message_type,
                    "agent_name":         row.agent_name,
                    "model_name":         row.model_name,
                    "message_at":         self._ts(row.message_at_utc),
                    "message_order":      row.message_order,
                    "completion_tokens":  row.completion_tokens,
                    "prompt_tokens":      row.prompt_tokens,
                    "total_tokens":       row.total_tokens,
                    "finish_reason":      row.finish_reason,
                }

                nodes.append(builder.node(CHATBOT_MESSAGE, node_id, properties))

                if row.conversation_id:
                    rels.append(builder.rel(
                        HAS_MESSAGE,
                        build_chatbot_conversation_id(row.conversation_id),
                        node_id,
                        start_label=CHATBOT_CONVERSATION,
                        end_label=CHATBOT_MESSAGE,
                        properties={"message_order": row.message_order},
                    ))
                else:
                    self._skip("conversation_id is None — skipping HAS_MESSAGE rel", row_id=row.message_id)

            except (TransformationError, CanonicalizationError) as exc:
                self._skip(str(exc), row_id=getattr(row, "message_id", None))

        log_transformation_finished(self._logger, record_count=len(nodes) + len(rels), table_name=MSG_SOURCE_NAME, run_id=self._run_id)
        return builder.batch(nodes, rels, batch_sequence=0)

    # -- ToolCall nodes + Tool nodes + USED_TOOL rels -------------------------

    def _transform_tool_calls(self, batch: ExtractorBatch) -> GraphWriteBatch:
        self._reset_skip_count()
        builder = GraphRecordBuilder(self._run_id, TOOL_SOURCE_NAME)
        nodes: list[NodeRecord] = []
        rels: list[RelationshipRecord] = []

        # Track emitted Tool nodes to deduplicate within batch
        seen_tool_names: set[str] = set()

        log_transformation_started(self._logger, table_name=TOOL_SOURCE_NAME, run_id=self._run_id)

        for row in batch.rows:
            row: ChatbotToolCallsRow
            try:
                if not row.tool_call_id:
                    raise TransformationError("Missing tool_call_id", source=TOOL_SOURCE_NAME)

                node_id = build_tool_call_id(row.tool_call_id)

                properties = {
                    "tool_name":      row.tool_name,
                    "tool_call_at":   self._ts(row.tool_call_at_utc),
                    "tool_arguments": row.tool_arguments,
                }

                nodes.append(builder.node(TOOL_CALL, node_id, properties))

                # Emit canonical Tool node — deduplicated by tool_name within batch
                if row.tool_name:
                    tool_node_id = slugify(row.tool_name)
                    if tool_node_id not in seen_tool_names:
                        seen_tool_names.add(tool_node_id)
                        nodes.append(builder.node(TOOL, tool_node_id, {"tool_name": row.tool_name}))

                # USED_TOOL (ChatbotMessage → ToolCall)
                if row.message_id:
                    rels.append(builder.rel(
                        USED_TOOL,
                        build_chatbot_message_id(row.message_id),
                        node_id,
                        start_label=CHATBOT_MESSAGE,
                        end_label=TOOL_CALL,
                        properties={"tool_name": row.tool_name},
                    ))
                else:
                    self._skip("message_id is None — skipping USED_TOOL rel", row_id=row.tool_call_id)

            except (TransformationError, CanonicalizationError) as exc:
                self._skip(str(exc), row_id=getattr(row, "tool_call_id", None))

        log_transformation_finished(self._logger, record_count=len(nodes) + len(rels), table_name=TOOL_SOURCE_NAME, run_id=self._run_id)
        return builder.batch(nodes, rels, batch_sequence=0)