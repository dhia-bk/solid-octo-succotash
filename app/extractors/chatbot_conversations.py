"""
Extractor for the dim_chatbot_conversations warehouse source.

Purpose:
- Extract AI chatbot conversation session rows from dim_chatbot_conversations,
  including user, source, message totals, token totals, model family, and
  demographic enrichments.
- Incremental strategy using conversation_start_utc as the watermark.
- Return typed ChatbotConversationsRow instances wrapped in ExtractorBatch.

Source characteristics:
    dim_chatbot_conversations holds one row per AI conversation session.
    Aggregate columns (total_messages, human_message_count, ai_message_count,
    total_tool_calls, total_tokens, duration_seconds, conversation_end_utc,
    conversation_length_category) are populated or updated as the conversation
    progresses and are finalized when the session ends.

    Filtering by conversation_start_utc captures new sessions correctly but
    may deliver incomplete aggregate values for in-progress conversations
    (those started since the last watermark but not yet ended). This is an
    accepted tradeoff — the majority of AI conversations complete within
    minutes; any in-progress row will have complete data on the next
    pipeline run when conversation_start_utc is already behind the watermark
    and the row is not re-extracted.

    Pipeline operators who need complete aggregate data on all conversations
    should use conversation_end_utc as an alternative watermark or schedule
    a bounded re-extraction window around recent conversation starts.

Design rules:
- conversation_id is VARCHAR(255); preserved as str.
- user_id is a string FK to dim_users; preserved as-is.
- user_country and user_gender are denormalized demographic enrichments
  snapshotted from dim_users at conversation time; preserved faithfully.
- model_family and first_tool_called are AI provenance fields; must not
  be dropped.
- No graph logic, canonicalization, or enrichment is applied here.

Source schema:
- Source table  : dim_chatbot_conversations
- Inclusion mode: GRAPH_CORE
- Graph entity  : ChatbotConversation
- Freshness field: conversation_start_utc
"""

from __future__ import annotations

from app.contracts.warehouse_rows import WarehouseRow
from app.extractors.base import BaseExtractor
from app.schemas.warehouse.chatbot_conversations import (
    FRESHNESS_FIELD,
    INCLUSION_MODE,
    PRIMARY_KEYS,
    SOURCE_NAME,
    ChatbotConversationsRow,
)


class ChatbotConversationsExtractor(BaseExtractor):
    """
    Extractor for dim_chatbot_conversations.

    Incremental strategy:
    - watermark field: conversation_start_utc
    - ordering: conversation_start_utc, conversation_id

    In-progress conversation limitation:
    - Aggregate columns (total_messages, total_tokens, duration_seconds,
      conversation_end_utc) may be incomplete for conversations that started
      since the last watermark but are still in progress at extraction time.
      Complete data arrives on the subsequent pipeline run for most sessions.
    """

    source_name: str = SOURCE_NAME
    schema_row_class: type[WarehouseRow] = ChatbotConversationsRow
    inclusion_mode: str = INCLUSION_MODE
    freshness_field: str | None = FRESHNESS_FIELD     # conversation_start_utc
    primary_key_fields: tuple[str, ...] = PRIMARY_KEYS
    default_chunk_size: int = 5000
    supports_incremental: bool = True

    # ── Source column contract ────────────────────────────────────────────────

    def get_source_columns(self) -> tuple[str, ...]:
        """
        Return the explicit ordered source columns for dim_chatbot_conversations.

        These columns must stay aligned with ChatbotConversationsRow.from_row().
        Adding or removing a column here requires a matching change in
        the schema row dataclass.

        Aggregate completeness note:
            total_messages, human_message_count, ai_message_count,
            total_tool_calls, total_tokens, duration_seconds,
            conversation_end_utc, and conversation_length_category may be
            incomplete for in-progress conversations. See class docstring.

        Provenance note:
            model_family and first_tool_called are AI lineage fields required
            for downstream model usage analytics; must not be dropped.

        Demographic note:
            user_country and user_gender are point-in-time snapshots from
            dim_users; preserved faithfully as denormalized enrichments.
        """
        return (
            "conversation_id",
            "user_id",
            "source",
            "conversation_start_utc",
            "conversation_end_utc",           # NULL for in-progress sessions
            "duration_seconds",               # NULL for in-progress sessions
            "total_messages",
            "human_message_count",
            "ai_message_count",
            "total_tool_calls",
            "total_tokens",
            "model_family",                   # AI provenance — must not be dropped
            "first_tool_called",
            "conversation_length_category",   # NULL for in-progress sessions
            "user_country",
            "user_gender",
        )

    # ── Query construction ────────────────────────────────────────────────────

    def build_base_query(self) -> str:
        """
        Return the base SELECT for dim_chatbot_conversations without
        incremental filtering.

        The incremental clause
        (WHERE conversation_start_utc > :watermark_value) is appended
        by the base runtime via build_incremental_clause().
        """
        columns = ",\n    ".join(self.get_source_columns())
        return f"""
SELECT
    {columns}
FROM {self.source_name}
""".strip()

    def build_incremental_clause(self, watermark_value: str | None) -> str:
        """
        Build the incremental filter using conversation_start_utc.

        Uses strict greater-than semantics so watermark advancement remains
        monotonic across runs. No clause is emitted on first run (watermark
        is None), triggering a full-table bootstrap load.
        """
        if not self.supports_incremental or not self.freshness_field:
            return ""

        if not watermark_value:
            return ""

        return f"\nWHERE {self.freshness_field} > :watermark_value"

    def build_order_by_clause(self) -> str:
        """
        Return stable deterministic ordering for dim_chatbot_conversations.

        conversation_start_utc first — aligns with watermark advancement and
        clusters output by session start time, which is the natural downstream
        consumption pattern for AI conversation analytics.

        conversation_id second — VARCHAR PK; breaks ties within the same
        start timestamp bucket deterministically.
        """
        return "\nORDER BY conversation_start_utc, conversation_id"

    def build_pagination_clause(self, limit: int, offset: int) -> str:
        """
        Return LIMIT/OFFSET pagination clause.
        """
        return "\nLIMIT %(limit)s OFFSET %(offset)s"