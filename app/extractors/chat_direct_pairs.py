"""
Extractor for the dim_chat_direct_pairs warehouse source.

Purpose:
- Extract user-to-user direct message pair aggregates from
  dim_chat_direct_pairs, including users, first/last message timestamps,
  and message/attachment counts.
- Incremental strategy using last_message_at as the watermark.
- Return typed ChatDirectPairsRow instances wrapped in ExtractorBatch.

Source characteristics:
    dim_chat_direct_pairs holds one row per unique user-user DM pair. The
    direct_pair_key is a DWH-normalized composite key, already order-
    normalized in the warehouse (A-B and B-A always produce the same key),
    so no additional participant ordering is needed at the extractor layer.

    All aggregate columns (conversation_count, total_messages,
    attachment_count, image_count) are updated in-place as the pair
    exchanges more messages. last_message_at advances with every new
    message, making it the correct incremental field — it naturally
    re-extracts pairs with new activity while skipping inactive pairs.
    This is the same watermark strategy used in chat_conversations.py.

Design rules:
- direct_pair_key is VARCHAR(255) and is the stable PK; preserved as str.
  The DWH guarantees order normalization; no additional sorting or
  deduplication of user_a_id / user_b_id is applied here.
- user_a_id and user_b_id are string FKs to dim_users; both must be
  preserved for DIRECT_MESSAGE edge construction.
- first_message_at is immutable after the pair's first exchange and is
  preserved for edge property construction (relationship start time).
- No graph logic, canonicalization, or enrichment is applied here.

Source schema:
- Source table  : dim_chat_direct_pairs
- Inclusion mode: GRAPH_CORE
- Graph entity  : DirectPair
- Freshness field: last_message_at
"""

from __future__ import annotations

from app.contracts.warehouse_rows import WarehouseRow
from app.extractors.base import BaseExtractor
from app.schemas.warehouse.chat_direct_pairs import (
    FRESHNESS_FIELD,
    INCLUSION_MODE,
    PRIMARY_KEYS,
    SOURCE_NAME,
    ChatDirectPairsRow,
)


class ChatDirectPairsExtractor(BaseExtractor):
    """
    Extractor for dim_chat_direct_pairs.

    Incremental strategy:
    - watermark field: last_message_at
    - ordering: last_message_at, direct_pair_key

    One-row-per-pair semantics:
    - The table is a current-state aggregate per user pair, not an event log.
    - Incremental runs capture only pairs that exchanged new messages since
      the last watermark; inactive pairs are correctly excluded.
    - The full-table bootstrap (no watermark) loads all pair aggregates.
    """

    source_name: str = SOURCE_NAME
    schema_row_class: type[WarehouseRow] = ChatDirectPairsRow
    inclusion_mode: str = INCLUSION_MODE
    freshness_field: str | None = FRESHNESS_FIELD     # last_message_at
    primary_key_fields: tuple[str, ...] = PRIMARY_KEYS
    default_chunk_size: int = 5000
    supports_incremental: bool = True

    # ── Source column contract ────────────────────────────────────────────────

    def get_source_columns(self) -> tuple[str, ...]:
        """
        Return the explicit ordered source columns for dim_chat_direct_pairs.

        These columns must stay aligned with ChatDirectPairsRow.from_row().
        Adding or removing a column here requires a matching change in
        the schema row dataclass.

        Key normalization note:
            direct_pair_key is already order-normalized in the DWH (A-B and
            B-A produce the same key). No additional participant ordering or
            deduplication is needed here or in the transformer.

        Participant FK note:
            user_a_id and user_b_id are both string FKs to dim_users. Both
            must be preserved for DIRECT_MESSAGE edge construction; neither
            should be treated as the canonical "sender" or "receiver".
        """
        return (
            "direct_pair_key",
            "user_a_id",
            "user_b_id",
            "conversation_count",
            "total_messages",
            "attachment_count",
            "image_count",
            "first_message_at",
            "last_message_at",
            "created_at",
        )

    # ── Query construction ────────────────────────────────────────────────────

    def build_base_query(self) -> str:
        """
        Return the base SELECT for dim_chat_direct_pairs without incremental
        filtering.

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
        is None), triggering a full-table bootstrap load of all pair aggregates.
        """
        if not self.supports_incremental or not self.freshness_field:
            return ""

        if not watermark_value:
            return ""

        return f"\nWHERE {self.freshness_field} > %(watermark_value)s"

    def build_order_by_clause(self) -> str:
        """
        Return stable deterministic ordering for dim_chat_direct_pairs.

        last_message_at first — aligns with watermark advancement and clusters
        output by most recent pair activity.

        direct_pair_key second — VARCHAR PK; breaks ties within the same
        last_message_at timestamp bucket deterministically.
        """
        return "\nORDER BY last_message_at, direct_pair_key"

    def build_pagination_clause(self, limit: int, offset: int) -> str:
        """
        Return LIMIT/OFFSET pagination clause.
        """
        return "\nLIMIT %(limit)s OFFSET %(offset)s"