"""
Warehouse schema for dim_chatbot_conversations.

Source table: dim_chatbot_conversations
Domain: ai_communication
Inclusion mode: GRAPH_CORE — direct graph node creation
Graph entity: ChatbotConversation
Freshness field: conversation_start_utc

AI chatbot conversation dimension. Feeds ChatbotConversation nodes and the
TALKED_TO relationship (User → ChatbotConversation).

DWH type note:
    conversation_id — VARCHAR(255) in DWH; str (spec suggested int).
    user_id         — VARCHAR(255) in DWH; str | None.
    Both timestamp fields are TIMESTAMP in the DWH.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.core.constants import CHATBOT_CONVERSATION, GRAPH_CORE
from app.core.ids import normalize_nullable_string_id, normalize_string_id
from app.core.time import warehouse_value_to_utc_datetime

# ── Module-level constants ────────────────────────────────────────────────────

SOURCE_NAME: str = "dim_chatbot_conversations"
INCLUSION_MODE: str = GRAPH_CORE
PRIMARY_KEYS: tuple[str, ...] = ("conversation_id",)
FRESHNESS_FIELD: str | None = "conversation_start_utc"
GRAPH_ENTITY_MAPPINGS: tuple[str, ...] = (CHATBOT_CONVERSATION,)


# ── Row shape ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ChatbotConversationsRow:
    """
    Typed row shape for dim_chatbot_conversations.

    conversation_id is VARCHAR(255) in the DWH; stored as str.
    """

    conversation_id: str
    user_id: str | None
    source: str | None
    conversation_start_utc: datetime | None
    conversation_end_utc: datetime | None
    duration_seconds: int | None
    total_messages: int | None
    human_message_count: int | None
    ai_message_count: int | None
    total_tool_calls: int | None
    total_tokens: int | None
    model_family: str | None
    first_tool_called: str | None
    conversation_length_category: str | None
    user_country: str | None
    user_gender: str | None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> ChatbotConversationsRow:
        """Normalize a raw warehouse row into a typed ChatbotConversationsRow."""
        return cls(
            conversation_id=normalize_string_id(row["conversation_id"], field_name="conversation_id"),
            user_id=normalize_nullable_string_id(row.get("user_id"), field_name="user_id"),
            source=row.get("source"),
            conversation_start_utc=warehouse_value_to_utc_datetime(row.get("conversation_start_utc")),
            conversation_end_utc=warehouse_value_to_utc_datetime(row.get("conversation_end_utc")),
            duration_seconds=int(row["duration_seconds"]) if row.get("duration_seconds") is not None else None,
            total_messages=int(row["total_messages"]) if row.get("total_messages") is not None else None,
            human_message_count=int(row["human_message_count"]) if row.get("human_message_count") is not None else None,
            ai_message_count=int(row["ai_message_count"]) if row.get("ai_message_count") is not None else None,
            total_tool_calls=int(row["total_tool_calls"]) if row.get("total_tool_calls") is not None else None,
            total_tokens=int(row["total_tokens"]) if row.get("total_tokens") is not None else None,
            model_family=row.get("model_family"),
            first_tool_called=row.get("first_tool_called"),
            conversation_length_category=row.get("conversation_length_category"),
            user_country=row.get("user_country"),
            user_gender=row.get("user_gender"),
        )
