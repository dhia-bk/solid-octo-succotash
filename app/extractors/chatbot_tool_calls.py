"""
Extractor for the fct_chatbot_tool_calls warehouse source.

Purpose:
- Extract tool invocation events from fct_chatbot_tool_calls, including
  tool name, arguments, timestamp, and conversation/message linkage.
- Incremental strategy using tool_call_at_utc as the watermark.
- Return typed ChatbotToolCallsRow instances wrapped in ExtractorBatch.

Source characteristics:
    fct_chatbot_tool_calls is an append-oriented event log — one row per
    tool invocation within a chatbot message. Rows are written once and not
    updated after initial insert; tool_call_at_utc is the authoritative
    event timestamp. Incremental extraction is therefore complete and correct
    with no mutation window required.

    Each row carries both message_id (FK to fct_chatbot_messages) and
    conversation_id (FK to dim_chatbot_conversations), providing two-level
    linkage for USED_TOOL edge construction. Both must be preserved.

    tool_arguments is a raw JSON string from the DWH. It is extracted
    faithfully as a string; parsing is the transformer's responsibility.
    The extractor does not validate or parse JSON content.

Design rules:
- tool_call_id, message_id, and conversation_id are VARCHAR(255); preserved
  as str / str | None. No SQL CAST applied.
- tool_call_date_key is an INTEGER partition label; stored as str | None.
- tool_arguments must be preserved as a raw string exactly as stored in the
  DWH; no JSON parsing, validation, or truncation is applied here.
- tool_name is an AI provenance field required for downstream tool usage
  analytics; must not be dropped.
- No graph logic, canonicalization, or enrichment is applied here.

Source schema:
- Source table  : fct_chatbot_tool_calls
- Inclusion mode: GRAPH_CORE
- Graph entity  : ToolCall
- Freshness field: tool_call_at_utc
"""

from __future__ import annotations

from app.contracts.warehouse_rows import WarehouseRow
from app.extractors.base import BaseExtractor
from app.schemas.warehouse.chatbot_tool_calls import (
    FRESHNESS_FIELD,
    INCLUSION_MODE,
    PRIMARY_KEYS,
    SOURCE_NAME,
    ChatbotToolCallsRow,
)


class ChatbotToolCallsExtractor(BaseExtractor):
    """
    Extractor for fct_chatbot_tool_calls.

    Incremental strategy:
    - watermark field: tool_call_at_utc
    - ordering: tool_call_at_utc, tool_call_id

    Append-oriented semantics:
    - Tool call rows are written once and not updated. Incremental extraction
      by tool_call_at_utc is therefore complete and correct.

    Dual linkage:
    - Each row carries both message_id and conversation_id. Both are preserved
      for USED_TOOL edge construction; the transformer decides which FK to
      follow for each edge type.

    Raw JSON arguments:
    - tool_arguments is extracted as a raw string. JSON parsing belongs to
      the transformer layer.
    """

    source_name: str = SOURCE_NAME
    schema_row_class: type[WarehouseRow] = ChatbotToolCallsRow
    inclusion_mode: str = INCLUSION_MODE
    freshness_field: str | None = FRESHNESS_FIELD     # tool_call_at_utc
    primary_key_fields: tuple[str, ...] = PRIMARY_KEYS
    default_chunk_size: int = 5000                    # volume tracks AI tool
                                                      # usage frequency
    supports_incremental: bool = True

    # ── Source column contract ────────────────────────────────────────────────

    def get_source_columns(self) -> tuple[str, ...]:
        """
        Return the explicit ordered source columns for fct_chatbot_tool_calls.

        These columns must stay aligned with ChatbotToolCallsRow.from_row().
        Adding or removing a column here requires a matching change in
        the schema row dataclass.

        Dual linkage note:
            message_id and conversation_id provide two-level FK linkage.
            Both must be present; the transformer determines which to follow
            for USED_TOOL edge construction.

        tool_arguments note:
            Raw JSON string from the DWH; extracted as-is. JSON parsing,
            validation, and schema enforcement belong to the transformer.
            Do not truncate or modify this field at the extractor layer.

        Partition label note:
            tool_call_date_key is an INTEGER in the DWH but is a partition
            label; stored as str | None. No arithmetic applied.
        """
        return (
            "tool_call_id",
            "message_id",            # FK to fct_chatbot_messages
            "conversation_id",       # FK to dim_chatbot_conversations
            "user_id",
            "tool_call_at_utc",
            "tool_call_date_key",    # INTEGER partition label; str | None
            "tool_name",             # AI provenance — must not be dropped
            "tool_arguments",        # raw JSON string — do not parse here
        )

    # ── Query construction ────────────────────────────────────────────────────

    def build_base_query(self) -> str:
        """
        Return the base SELECT for fct_chatbot_tool_calls without incremental
        filtering.

        The incremental clause (WHERE tool_call_at_utc > :watermark_value)
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
        Build the incremental filter using tool_call_at_utc.

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
        Return stable deterministic ordering for fct_chatbot_tool_calls.

        tool_call_at_utc first — aligns with watermark advancement and
        clusters output by invocation time.

        tool_call_id second — VARCHAR PK; breaks ties within the same
        timestamp bucket deterministically.
        """
        return "\nORDER BY tool_call_at_utc, tool_call_id"

    def build_pagination_clause(self, limit: int, offset: int) -> str:
        """
        Return LIMIT/OFFSET pagination clause.
        """
        return "\nLIMIT %(limit)s OFFSET %(offset)s"