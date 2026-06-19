"""
Warehouse schema for dim_chat_conversations_mysql.

Source table: dim_chat_conversations_mysql
Domain: social
Inclusion mode: GRAPH_CORE — direct graph node creation
Graph entity: Conversation
Freshness field: last_message_at

Group and direct chat conversation dimension. Covers both private league
group chats and direct-message conversation containers. Feeds the
DIRECT_MESSAGE relationship context.

DWH type notes:
    conversation_id    — VARCHAR(100) in DWH; str.
    created_by_user_id — VARCHAR(100) in DWH; str | None.
    direct_pair_key    — VARCHAR(255); str | None (present for DM conversations,
                         null for group chats).
    is_active          — TINYINT 0/1 flag.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.core.constants import CONVERSATION, GRAPH_CORE
from app.core.ids import normalize_nullable_string_id, normalize_string_id
from app.core.time import warehouse_value_to_utc_datetime

# ── Module-level constants ────────────────────────────────────────────────────

SOURCE_NAME: str = "dim_chat_conversations_mysql"
INCLUSION_MODE: str = GRAPH_CORE
PRIMARY_KEYS: tuple[str, ...] = ("conversation_id",)
FRESHNESS_FIELD: str | None = "last_message_at"
GRAPH_ENTITY_MAPPINGS: tuple[str, ...] = (CONVERSATION,)


# ── Row shape ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ChatConversationsRow:
    """
    Typed row shape for dim_chat_conversations_mysql.

    TINYINT fields (0/1 integers, not booleans in the DWH):
        is_active

    direct_pair_key is present only for direct-message conversations;
    null for group chats.
    """

    conversation_id: str
    conversation_type: str | None
    private_league_id: int | None
    created_by_user_id: str | None
    conversation_name: str | None
    is_active: int | None
    last_message_at: datetime | None
    participant_count: int | None
    total_messages: int | None
    created_at_utc: datetime | None
    direct_pair_key: str | None
    attachment_count: int | None
    image_count: int | None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> ChatConversationsRow:
        """Normalize a raw warehouse row into a typed ChatConversationsRow."""
        return cls(
            conversation_id=normalize_string_id(row["conversation_id"], field_name="conversation_id"),
            conversation_type=row.get("conversation_type"),
            private_league_id=int(row["private_league_id"]) if row.get("private_league_id") is not None else None,
            created_by_user_id=normalize_nullable_string_id(row.get("created_by_user_id"), field_name="created_by_user_id"),
            conversation_name=row.get("conversation_name"),
            is_active=int(row["is_active"]) if row.get("is_active") is not None else None,
            last_message_at=warehouse_value_to_utc_datetime(row.get("last_message_at")),
            participant_count=int(row["participant_count"]) if row.get("participant_count") is not None else None,
            total_messages=int(row["total_messages"]) if row.get("total_messages") is not None else None,
            created_at_utc=warehouse_value_to_utc_datetime(row.get("created_at_utc")),
            direct_pair_key=normalize_nullable_string_id(row.get("direct_pair_key"), field_name="direct_pair_key"),
            attachment_count=int(row["attachment_count"]) if row.get("attachment_count") is not None else None,
            image_count=int(row["image_count"]) if row.get("image_count") is not None else None,
        )
