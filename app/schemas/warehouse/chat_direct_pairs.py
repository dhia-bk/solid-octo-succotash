"""
Warehouse schema for dim_chat_direct_pairs.

Source table: dim_chat_direct_pairs
Domain: social
Inclusion mode: GRAPH_CORE — direct graph node creation
Graph entity: DirectPair
Freshness field: last_message_at

User-to-user direct message pair aggregates. direct_pair_key is a normalized
composite user-user key already stable in the DWH (order-normalized so A-B
and B-A produce the same key). Feeds DIRECT_MESSAGE relationship (User → DirectPair).

DWH type notes:
    direct_pair_key — VARCHAR(255) PK; str.
    user_a_id       — VARCHAR(255); str | None.
    user_b_id       — VARCHAR(255); str | None.
    All datetime fields — DATETIME in DWH.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.core.constants import DIRECT_PAIR, GRAPH_CORE
from app.core.ids import normalize_nullable_string_id, normalize_string_id
from app.core.time import warehouse_value_to_utc_datetime

# ── Module-level constants ────────────────────────────────────────────────────

SOURCE_NAME: str = "dim_chat_direct_pairs"
INCLUSION_MODE: str = GRAPH_CORE
PRIMARY_KEYS: tuple[str, ...] = ("direct_pair_key",)
FRESHNESS_FIELD: str | None = "last_message_at"
GRAPH_ENTITY_MAPPINGS: tuple[str, ...] = (DIRECT_PAIR,)


# ── Row shape ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ChatDirectPairsRow:
    """
    Typed row shape for dim_chat_direct_pairs.

    direct_pair_key is the DWH-normalized composite user-user key.
    user_a_id and user_b_id are the two participants; the key is order-
    normalized in the DWH so no additional sorting is needed here.
    """

    direct_pair_key: str
    user_a_id: str | None
    user_b_id: str | None
    conversation_count: int | None
    total_messages: int | None
    attachment_count: int | None
    image_count: int | None
    first_message_at: datetime | None
    last_message_at: datetime | None
    created_at: datetime | None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> ChatDirectPairsRow:
        """Normalize a raw warehouse row into a typed ChatDirectPairsRow."""
        return cls(
            direct_pair_key=normalize_string_id(row["direct_pair_key"], field_name="direct_pair_key"),
            user_a_id=normalize_nullable_string_id(row.get("user_a_id"), field_name="user_a_id"),
            user_b_id=normalize_nullable_string_id(row.get("user_b_id"), field_name="user_b_id"),
            conversation_count=int(row["conversation_count"]) if row.get("conversation_count") is not None else None,
            total_messages=int(row["total_messages"]) if row.get("total_messages") is not None else None,
            attachment_count=int(row["attachment_count"]) if row.get("attachment_count") is not None else None,
            image_count=int(row["image_count"]) if row.get("image_count") is not None else None,
            first_message_at=warehouse_value_to_utc_datetime(row.get("first_message_at")),
            last_message_at=warehouse_value_to_utc_datetime(row.get("last_message_at")),
            created_at=warehouse_value_to_utc_datetime(row.get("created_at")),
        )
