"""
Extractor for the dim_chat_conversations_mysql warehouse source.

Purpose:
- Extract social chat conversation identity rows from
  dim_chat_conversations_mysql, including conversation_id, type,
  private_league_id, creator, last message time, participants, and
  engagement totals.
- Incremental strategy using last_message_at as the watermark.
- Return typed ChatConversationsRow instances wrapped in ExtractorBatch.

Source characteristics:
    dim_chat_conversations_mysql covers both group chats (anchored to a
    private league via private_league_id) and direct-message conversations
    (identified by a non-NULL direct_pair_key). A row represents the
    conversation container, not individual messages.

    last_message_at advances each time a new message is sent, making it
    the correct incremental field — it captures both newly created
    conversations and existing conversations that received new activity
    since the last pipeline run. This is preferable to created_at_utc,
    which would miss engagement updates on older conversations.

    participant_count, total_messages, attachment_count, and image_count
    are running aggregates that update in-place as the conversation grows.
    Filtering by last_message_at naturally re-extracts conversations with
    new activity, keeping these aggregates fresh on active conversations.
    Conversations that become inactive (no new messages) will not be
    re-extracted until activity resumes, which is the correct behaviour.

Conversation type routing:
    conversation_type distinguishes group chats from DM conversations.
    direct_pair_key is non-NULL only for DM conversations and NULL for
    group chats. Both fields must be preserved so the transformer can
    route DIRECT_MESSAGE edges and MEMBER_OF (conversation) edges correctly.

Design rules:
- conversation_id is VARCHAR(100); preserved as str.
- private_league_id is an integer FK to dim_private_leagues; preserved as-is.
- direct_pair_key is VARCHAR(255); NULL for group chats, non-NULL for DMs.
  Both states are semantically significant; the extractor must not filter
  on this field.
- No graph logic, canonicalization, or enrichment is applied here.

Source schema:
- Source table  : dim_chat_conversations_mysql
- Inclusion mode: GRAPH_CORE
- Graph entity  : Conversation
- Freshness field: last_message_at
"""

from __future__ import annotations

from app.contracts.warehouse_rows import WarehouseRow
from app.extractors.base import BaseExtractor
from app.schemas.warehouse.chat_conversations import (
    FRESHNESS_FIELD,
    INCLUSION_MODE,
    PRIMARY_KEYS,
    SOURCE_NAME,
    ChatConversationsRow,
)


class ChatConversationsExtractor(BaseExtractor):
    """
    Extractor for dim_chat_conversations_mysql.

    Incremental strategy:
    - watermark field: last_message_at
    - ordering: last_message_at, conversation_id

    Activity-driven watermark:
    - last_message_at advances on every new message, so incremental runs
      capture both new conversations and conversations with new activity.
      Inactive conversations (no new messages since last watermark) are
      correctly excluded until activity resumes.

    Dual conversation type:
    - Group chats: private_league_id is non-NULL; direct_pair_key is NULL.
    - DM conversations: direct_pair_key is non-NULL; private_league_id is NULL.
      Both types are extracted uniformly; the transformer routes them.
    """

    source_name: str = SOURCE_NAME
    schema_row_class: type[WarehouseRow] = ChatConversationsRow
    inclusion_mode: str = INCLUSION_MODE
    freshness_field: str | None = FRESHNESS_FIELD     # last_message_at
    primary_key_fields: tuple[str, ...] = PRIMARY_KEYS
    default_chunk_size: int = 5000
    supports_incremental: bool = True

    # ── Source column contract ────────────────────────────────────────────────

    def get_source_columns(self) -> tuple[str, ...]:
        """
        Return the explicit ordered source columns for dim_chat_conversations_mysql.

        These columns must stay aligned with ChatConversationsRow.from_row().
        Adding or removing a column here requires a matching change in
        the schema row dataclass.

        Conversation type routing note:
            conversation_type and direct_pair_key together identify the
            conversation variant. direct_pair_key is NULL for group chats
            and non-NULL for DM conversations. Do not filter on either field;
            routing belongs to the transformer layer.

        private_league_id note:
            INTEGER FK to dim_private_leagues. Non-NULL for group chats,
            NULL for DM conversations.
        """
        return (
            "conversation_id",
            "conversation_type",
            "private_league_id",    # non-NULL for group chats; NULL for DMs
            "created_by_user_id",
            "conversation_name",
            "is_active",
            "last_message_at",
            "participant_count",
            "total_messages",
            "created_at_utc",
            "direct_pair_key",      # non-NULL for DMs; NULL for group chats
            "attachment_count",
            "image_count",
        )

    # ── Query construction ────────────────────────────────────────────────────

    def build_base_query(self) -> str:
        """
        Return the base SELECT for dim_chat_conversations_mysql without
        incremental filtering.

        The incremental clause (WHERE last_message_at > %(watermark_value)s)
        is appended by the base runtime via build_incremental_clause().
        """
        columns = ",\n    ".join(self.get_source_columns())
        return f"""
SELECT
    {columns}
FROM {self.source_name}
""".strip()

    def build_incremental_clause(self, watermark_value: str | None) -> str:
        """
        Build the incremental filter using last_message_at.

        Uses strict greater-than semantics so watermark advancement remains
        monotonic across runs. No clause is emitted on first run (watermark
        is None), triggering a full-table bootstrap load.
        """
        if not self.supports_incremental or not self.freshness_field:
            return ""

        if not watermark_value:
            return ""

        return f"\nWHERE {self.freshness_field} > %(watermark_value)s"

    def build_order_by_clause(self) -> str:
        """
        Return stable deterministic ordering for dim_chat_conversations_mysql.

        last_message_at first — aligns with watermark advancement and clusters
        output by most recent activity, reflecting the natural downstream
        consumption pattern for conversation ingestion.

        conversation_id second — VARCHAR PK; breaks ties within the same
        last_message_at timestamp bucket deterministically.
        """
        return "\nORDER BY last_message_at, conversation_id"

    def build_pagination_clause(self, limit: int, offset: int) -> str:
        """
        Return LIMIT/OFFSET pagination clause.
        """
        return "\nLIMIT %(limit)s OFFSET %(offset)s"