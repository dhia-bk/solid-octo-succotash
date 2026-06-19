"""
Warehouse schema for fct_chatbot_tool_calls.

Source table: fct_chatbot_tool_calls
Domain: ai_communication
Inclusion mode: GRAPH_CORE — direct graph node creation
Graph entity: ToolCall
Freshness field: tool_call_at_utc

Tool invocations within chatbot messages. Feeds ToolCall nodes and the
USED_TOOL relationship (ChatbotMessage → ToolCall).

DWH type notes:
    tool_call_id    — VARCHAR(255) in DWH; str.
    message_id      — VARCHAR(255) in DWH; str | None (spec suggested int).
    conversation_id — VARCHAR(255) in DWH; str | None (spec suggested int).
    user_id         — VARCHAR(255) in DWH; str | None.
    tool_call_date_key — INTEGER partition key; str | None (partition label).
    tool_arguments  — TEXT in DWH; raw JSON string, not parsed at schema layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.core.constants import GRAPH_CORE, TOOL_CALL
from app.core.ids import normalize_nullable_string_id, normalize_string_id
from app.core.time import warehouse_value_to_utc_datetime

# ── Module-level constants ────────────────────────────────────────────────────

SOURCE_NAME: str = "fct_chatbot_tool_calls"
INCLUSION_MODE: str = GRAPH_CORE
PRIMARY_KEYS: tuple[str, ...] = ("tool_call_id",)
FRESHNESS_FIELD: str | None = "tool_call_at_utc"
GRAPH_ENTITY_MAPPINGS: tuple[str, ...] = (TOOL_CALL,)


# ── Row shape ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ChatbotToolCallsRow:
    """
    Typed row shape for fct_chatbot_tool_calls.

    tool_call_id, message_id, and conversation_id are VARCHAR(255) in the DWH;
    stored as str / str | None.

    tool_call_date_key is an INTEGER partition key; str | None.

    tool_arguments is a raw JSON string from the DWH. Parsing is the
    transformer's responsibility — do not parse at this layer.
    """

    tool_call_id: str
    message_id: str | None
    conversation_id: str | None
    user_id: str | None
    tool_call_at_utc: datetime | None
    tool_call_date_key: str | None
    tool_name: str | None
    tool_arguments: str | None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> ChatbotToolCallsRow:
        """Normalize a raw warehouse row into a typed ChatbotToolCallsRow."""
        return cls(
            tool_call_id=normalize_string_id(row["tool_call_id"], field_name="tool_call_id"),
            message_id=normalize_nullable_string_id(row.get("message_id"), field_name="message_id"),
            conversation_id=normalize_nullable_string_id(row.get("conversation_id"), field_name="conversation_id"),
            user_id=normalize_nullable_string_id(row.get("user_id"), field_name="user_id"),
            tool_call_at_utc=warehouse_value_to_utc_datetime(row.get("tool_call_at_utc")),
            tool_call_date_key=str(row["tool_call_date_key"]) if row.get("tool_call_date_key") is not None else None,
            tool_name=row.get("tool_name"),
            tool_arguments=row.get("tool_arguments"),
        )
