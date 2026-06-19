"""
Merge queries for chatbot conversations, messages, and tool calls.
Source(s): dim_chatbot_conversations, fct_chatbot_messages, fct_chatbot_tool_calls
"""

from __future__ import annotations

from app.loaders.merge_queries.base import build_node_merge_query


def get_chatbot_conversation_merge_query(
    source_name: str = "dim_chatbot_conversations",
) -> str:
    """Return Cypher MERGE query for ChatbotConversation nodes."""
    return build_node_merge_query(
        label="ChatbotConversation",
        merge_key_field="id",
        write_once_fields=["conversation_start", "first_message_at"],
        mutable_fields=[
            "last_message_at",
            "message_count",
            "resolution_status",
            "session_id",
        ],
    )


def get_chatbot_message_merge_query(
    source_name: str = "fct_chatbot_messages",
) -> str:
    """Return Cypher MERGE query for ChatbotMessage nodes."""
    return build_node_merge_query(
        label="ChatbotMessage",
        merge_key_field="id",
        write_once_fields=[],
        mutable_fields=[
            "conversation_id",
            "role",
            "content_preview",
            "sent_at",
            "token_count",
            "tool_used",
        ],
    )


def get_tool_call_merge_query(
    source_name: str = "fct_chatbot_tool_calls",
) -> str:
    """Return Cypher MERGE query for ToolCall nodes."""
    return build_node_merge_query(
        label="ToolCall",
        merge_key_field="id",
        write_once_fields=[],
        mutable_fields=[
            "message_id",
            "tool_name",
            "tool_type",
            "input_summary",
            "output_summary",
            "called_at",
            "duration_ms",
        ],
    )
