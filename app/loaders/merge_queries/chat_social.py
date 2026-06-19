"""
Merge queries for chat and social messaging.
Source(s): dim_chat_conversations_mysql, dim_chat_direct_pairs, fct_chat_messages,
           dim_chatbot_conversations, fct_chatbot_messages, fct_chatbot_tool_calls,
           dim_ai_articles
"""

from __future__ import annotations

from app.loaders.merge_queries.base import (
    build_node_merge_query,
    build_relationship_merge_query,
)


def get_conversation_merge_query(
    source_name: str = "dim_chat_conversations_mysql",
) -> str:
    """Return Cypher MERGE query for Conversation from source_name."""
    return build_node_merge_query(
        label="Conversation",
        merge_key_field="id",
        write_once_fields=["conversation_start"],
        mutable_fields=[
            "participant_count",
            "last_message_at",
            "is_active",
        ],
    )


def get_direct_pair_merge_query(source_name: str = "dim_chat_direct_pairs") -> str:
    """Return Cypher MERGE query for DirectPair from source_name."""
    return build_node_merge_query(
        label="DirectPair",
        merge_key_field="id",
        write_once_fields=["first_seen_at"],
        mutable_fields=[
            "user1_id",
            "user2_id",
            "message_count",
        ],
    )


def get_direct_message_merge_query(source_name: str = "fct_chat_messages") -> str:
    """Return Cypher MERGE query for DIRECT_MESSAGE (User→DirectPair) from source_name."""
    return build_relationship_merge_query(
        rel_type="DIRECT_MESSAGE",
        start_label="User",
        end_label="DirectPair",
        start_merge_field="id",
        end_merge_field="id",
        rel_merge_fields=["message_id"],
        rel_property_fields=["sent_at", "message_type"],
    )


def get_talked_to_merge_query(source_name: str = "dim_chatbot_conversations") -> str:
    """Return Cypher MERGE query for TALKED_TO (User→ChatbotConversation) from source_name."""
    return build_relationship_merge_query(
        rel_type="TALKED_TO",
        start_label="User",
        end_label="ChatbotConversation",
        start_merge_field="id",
        end_merge_field="id",
        rel_merge_fields=None,
        rel_property_fields=["conversation_start"],
    )


def get_has_message_merge_query(source_name: str = "fct_chatbot_messages") -> str:
    """Return Cypher MERGE query for HAS_MESSAGE (ChatbotConversation→ChatbotMessage) from source_name."""
    return build_relationship_merge_query(
        rel_type="HAS_MESSAGE",
        start_label="ChatbotConversation",
        end_label="ChatbotMessage",
        start_merge_field="id",
        end_merge_field="id",
        rel_merge_fields=None,
        rel_property_fields=[],
    )


def get_used_tool_merge_query(source_name: str = "fct_chatbot_tool_calls") -> str:
    """Return Cypher MERGE query for USED_TOOL (ChatbotMessage→ToolCall) from source_name."""
    return build_relationship_merge_query(
        rel_type="USED_TOOL",
        start_label="ChatbotMessage",
        end_label="ToolCall",
        start_merge_field="id",
        end_merge_field="id",
        rel_merge_fields=None,
        rel_property_fields=[],
    )


def get_generated_for_merge_query(source_name: str = "dim_ai_articles") -> str:
    """Return Cypher MERGE query for GENERATED_FOR (AIArticle→User) from source_name."""
    return build_relationship_merge_query(
        rel_type="GENERATED_FOR",
        start_label="AIArticle",
        end_label="User",
        start_merge_field="id",
        end_merge_field="id",
        rel_merge_fields=None,
        rel_property_fields=["generated_at"],
    )
