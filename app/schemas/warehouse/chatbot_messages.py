"""
Warehouse schema for fct_chatbot_messages.

Source table: fct_chatbot_messages
Domain: ai_communication
Inclusion mode: GRAPH_CORE — direct graph node creation
Graph entity: ChatbotMessage
Freshness field: message_at_utc

Individual chatbot message events. Feeds ChatbotMessage nodes and the
HAS_MESSAGE relationship (ChatbotConversation → ChatbotMessage).

DWH type notes:
    message_id      — VARCHAR(255) in DWH; str (spec suggested int).
    conversation_id — VARCHAR(255) in DWH; str | None (spec suggested int).
    user_id         — VARCHAR(255) in DWH; str | None.
    message_at_utc  — VARCHAR(255) in DWH (stored as ISO string, not a
                      native DATETIME column); normalized via
                      warehouse_value_to_utc_datetime which handles string
                      input safely.
    message_date_key — INTEGER partition key; str | None (partition label).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.core.constants import CHATBOT_MESSAGE, GRAPH_CORE
from app.core.ids import normalize_nullable_string_id, normalize_string_id
from app.core.time import warehouse_value_to_utc_datetime

# ── Module-level constants ────────────────────────────────────────────────────

SOURCE_NAME: str = "fct_chatbot_messages"
INCLUSION_MODE: str = GRAPH_CORE
PRIMARY_KEYS: tuple[str, ...] = ("message_id",)
FRESHNESS_FIELD: str | None = "message_at_utc"
GRAPH_ENTITY_MAPPINGS: tuple[str, ...] = (CHATBOT_MESSAGE,)


# ── Row shape ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ChatbotMessagesRow:
    """
    Typed row shape for fct_chatbot_messages.

    message_id and conversation_id are VARCHAR(255) in the DWH; stored as
    str / str | None.

    message_at_utc is VARCHAR(255) in the DWH (ISO string, not a native
    DATETIME column). warehouse_value_to_utc_datetime handles both string
    and datetime inputs safely, so the field type is datetime | None here.

    message_date_key is an INTEGER partition key; str | None.
    """

    message_id: str
    conversation_id: str | None
    user_id: str | None
    message_at_utc: datetime | None
    message_date_key: str | None
    message_order: int | None
    message_type: str | None
    agent_name: str | None
    model_name: str | None
    finish_reason: str | None
    completion_tokens: int | None
    prompt_tokens: int | None
    total_tokens: int | None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> ChatbotMessagesRow:
        """Normalize a raw warehouse row into a typed ChatbotMessagesRow."""
        return cls(
            message_id=normalize_string_id(row["message_id"], field_name="message_id"),
            conversation_id=normalize_nullable_string_id(row.get("conversation_id"), field_name="conversation_id"),
            user_id=normalize_nullable_string_id(row.get("user_id"), field_name="user_id"),
            message_at_utc=warehouse_value_to_utc_datetime(row.get("message_at_utc")),
            message_date_key=str(row["message_date_key"]) if row.get("message_date_key") is not None else None,
            message_order=int(row["message_order"]) if row.get("message_order") is not None else None,
            message_type=row.get("message_type"),
            agent_name=row.get("agent_name"),
            model_name=row.get("model_name"),
            finish_reason=row.get("finish_reason"),
            completion_tokens=int(row["completion_tokens"]) if row.get("completion_tokens") is not None else None,
            prompt_tokens=int(row["prompt_tokens"]) if row.get("prompt_tokens") is not None else None,
            total_tokens=int(row["total_tokens"]) if row.get("total_tokens") is not None else None,
        )
