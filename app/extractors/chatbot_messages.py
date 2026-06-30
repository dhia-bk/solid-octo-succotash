"""
Extractor for the fct_chatbot_messages warehouse source.

Purpose:
- Extract individual AI chatbot message events from fct_chatbot_messages,
  including message ordering, token usage, message type, and model metadata.
- Incremental strategy using message_at_utc as the watermark.
- Return typed ChatbotMessagesRow instances wrapped in ExtractorBatch.

Source characteristics:
    fct_chatbot_messages is an append-oriented event log — one row per
    message within a chatbot conversation. Messages are not updated after
    initial write; message_at_utc is the authoritative event timestamp.

    message_at_utc is VARCHAR(255) in the DWH (stored as ISO string, not a
    native DATETIME column). The watermark comparison in the incremental
    clause performs a string comparison against the DWH column. This is safe
    as long as the ISO format is consistently zero-padded (YYYY-MM-DDTHH:MM:SS
    or YYYY-MM-DD HH:MM:SS) — string and datetime ordering are equivalent
    under these conditions. warehouse_value_to_utc_datetime in from_row()
    handles the Python-level normalization to a proper datetime object.

Three-column ordering — message_at_utc, message_order, message_id:
    message_at_utc first — aligns with watermark advancement.
    message_order second  — within the same timestamp, orders messages by
                            their position within the conversation, which is
                            the semantically correct sequence for downstream
                            conversation reconstruction and HAS_MESSAGE edge
                            ordering.
    message_id third      — VARCHAR PK tiebreaker for the rare case of
                            identical timestamp and message_order values
                            across different conversations.

Design rules:
- message_id and conversation_id are VARCHAR(255); preserved as str / str | None.
- conversation_id is a FK to dim_chatbot_conversations; preserved as-is for
  HAS_MESSAGE edge construction.
- message_date_key is an INTEGER partition label; stored as str | None.
- agent_name, model_name, and finish_reason are AI provenance fields; must
  not be dropped.
- completion_tokens, prompt_tokens, and total_tokens are token usage metrics
  required for downstream AI cost and usage analytics.
- No graph logic, canonicalization, or enrichment is applied here.

Source schema:
- Source table  : fct_chatbot_messages
- Inclusion mode: GRAPH_CORE
- Graph entity  : ChatbotMessage
- Freshness field: message_at_utc (VARCHAR ISO string in DWH)
"""

from __future__ import annotations

from app.contracts.warehouse_rows import WarehouseRow
from app.extractors.base import BaseExtractor
from app.schemas.warehouse.chatbot_messages import (
    FRESHNESS_FIELD,
    INCLUSION_MODE,
    PRIMARY_KEYS,
    SOURCE_NAME,
    ChatbotMessagesRow,
)


class ChatbotMessagesExtractor(BaseExtractor):
    """
    Extractor for fct_chatbot_messages.

    Incremental strategy:
    - watermark field: message_at_utc
    - ordering: message_at_utc, message_order, message_id

    VARCHAR timestamp note:
    - message_at_utc is stored as an ISO string in the DWH, not a native
      DATETIME. The incremental WHERE clause compares strings directly.
      This is correct as long as the ISO format is consistently zero-padded;
      string and datetime ordering are equivalent under that condition.

    Append-oriented semantics:
    - Messages are written once and not updated. Incremental extraction is
      therefore complete and correct with no mutation window required.
    """

    source_name: str = SOURCE_NAME
    schema_row_class: type[WarehouseRow] = ChatbotMessagesRow
    inclusion_mode: str = INCLUSION_MODE
    freshness_field: str | None = FRESHNESS_FIELD     # message_at_utc
    primary_key_fields: tuple[str, ...] = PRIMARY_KEYS
    default_chunk_size: int = 5000                    # message volume tracks
                                                      # AI conversation usage
    supports_incremental: bool = True

    # ── Source column contract ────────────────────────────────────────────────

    def get_source_columns(self) -> tuple[str, ...]:
        """
        Return the explicit ordered source columns for fct_chatbot_messages.

        These columns must stay aligned with ChatbotMessagesRow.from_row().
        Adding or removing a column here requires a matching change in
        the schema row dataclass.

        VARCHAR timestamp note:
            message_at_utc is stored as an ISO string in the DWH. Selected
            as-is; from_row() normalises to datetime via
            warehouse_value_to_utc_datetime. No SQL CAST applied.

        Provenance fields:
            agent_name, model_name, finish_reason — AI lineage fields for
            downstream cost attribution and model usage analytics. Must not
            be dropped.

        Token usage fields:
            completion_tokens, prompt_tokens, total_tokens — required for
            downstream AI cost and usage aggregation. Must not be dropped.
        """
        return (
            "message_id",
            "conversation_id",     # FK to dim_chatbot_conversations
            "user_id",
            "message_at_utc",      # VARCHAR ISO string in DWH; see note
            "message_date_key",    # INTEGER partition label; str | None
            "message_order",       # position within conversation
            "message_type",
            "agent_name",          # AI provenance — must not be dropped
            "model_name",          # AI provenance — must not be dropped
            "finish_reason",       # AI provenance — must not be dropped
            "completion_tokens",
            "prompt_tokens",
            "total_tokens",
        )

    # ── Query construction ────────────────────────────────────────────────────

    def build_base_query(self) -> str:
        """
        Return the base SELECT for fct_chatbot_messages without incremental
        filtering.

        The incremental clause (WHERE message_at_utc > :watermark_value)
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
        Build the incremental filter using message_at_utc.

        Uses strict greater-than semantics so watermark advancement remains
        monotonic across runs. String comparison against the VARCHAR ISO
        timestamp column is valid as long as the stored format is consistently
        zero-padded. No clause is emitted on first run, triggering a
        full-table bootstrap load.
        """
        if not self.supports_incremental or not self.freshness_field:
            return ""

        if not watermark_value:
            return ""

        return f"\nWHERE {self.freshness_field} > :watermark_value"

    def build_order_by_clause(self) -> str:
        """
        Return stable deterministic ordering for fct_chatbot_messages.

        message_at_utc first — aligns with watermark advancement.

        message_order second — within the same timestamp, orders messages
        by their position within the conversation. This is the semantically
        correct sequence for downstream HAS_MESSAGE edge ordering and
        conversation reconstruction.

        message_id third — VARCHAR PK; tiebreaker for the rare case of
        identical timestamp and message_order values across different
        conversations (e.g. two conversations with their first message at
        the same second).
        """
        return "\nORDER BY message_at_utc, message_order, message_id"

    def build_pagination_clause(self, limit: int, offset: int) -> str:
        """
        Return LIMIT/OFFSET pagination clause.
        """
        return "\nLIMIT %(limit)s OFFSET %(offset)s"