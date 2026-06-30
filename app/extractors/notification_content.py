"""
Extractor for the dim_notification_content warehouse source.

Purpose:
- Extract deduplicated notification message catalog rows from
  dim_notification_content, including content identity, sender linkage,
  normalized and sample message text, and first/last seen timestamps.
- Incremental strategy using last_seen_at_utc as the watermark.
- Return typed NotificationContentRow instances wrapped in ExtractorBatch.

No declared primary key:
    dim_notification_content has no declared PK constraint in the DWH.
    content_id is VARCHAR(100) and is treated as the stable de facto key
    at extraction time. The extractor must not attempt to deduplicate rows —
    that is a transformer concern if duplicates are detected. Stable ordering
    by last_seen_at_utc, content_id ensures deterministic output across runs.

Watermark field — last_seen_at_utc:
    last_seen_at_utc is the correct incremental field for this source because
    dim_notification_content is a deduplicated message catalog — rows mutate
    as the same normalized message text is observed across additional
    notification events:
    - last_seen_at_utc advances each time the message is seen again
    - last_seen_date_key is updated correspondingly
    Incremental runs therefore capture all content rows whose reach has
    expanded since the previous run, not only newly observed message content.

Nullable sender field:
    sender_user_id is NULL for system-generated or anonymous notifications.
    Extracted faithfully as NULL; the transformer gates sender-edge creation
    on non-NULL values.

Partition key fields:
    first_seen_date_key and last_seen_date_key are INTEGER partition keys in
    the DWH, coerced to str | None in the row dataclass. Extracted as-is;
    interpretation is a transformer concern.

Design rules:
- content_id is VARCHAR(100) with no declared PK constraint; treated as the
  stable de facto key and used as the ordering tiebreaker.
- Deduplication is a transformer concern; the extractor emits rows as
  received from the warehouse.
- No graph logic, canonicalization, or enrichment is applied here.

Source schema:
- Source table  : dim_notification_content
- Inclusion mode: GRAPH_CORE
- Graph entity  : NotificationContent
- Freshness field: last_seen_at_utc
- Declared PK   : None (content_id treated as stable de facto key)
"""

from __future__ import annotations

from app.contracts.warehouse_rows import WarehouseRow
from app.extractors.base import BaseExtractor
from app.schemas.warehouse.notification_content import (
    FRESHNESS_FIELD,
    INCLUSION_MODE,
    PRIMARY_KEYS,
    SOURCE_NAME,
    NotificationContentRow,
)


class NotificationContentExtractor(BaseExtractor):
    """
    Extractor for dim_notification_content.

    Incremental strategy:
    - watermark field: last_seen_at_utc
    - ordering: last_seen_at_utc, content_id

    Mutation coverage:
    - last_seen_at_utc advances each time a deduplicated message is observed
      again, ensuring incremental runs capture content rows with expanded
      reach since the previous run, not only newly observed messages.

    Nullable sender field:
    - sender_user_id is NULL for system-generated or anonymous notifications.
      Extracted faithfully; transformer gates sender-edge creation on
      non-NULL values.

    No declared PK:
    - content_id is treated as the stable de facto key. The extractor
      preserves all rows as received; deduplication is a transformer concern.
    """

    source_name: str = SOURCE_NAME
    schema_row_class: type[WarehouseRow] = NotificationContentRow
    inclusion_mode: str = INCLUSION_MODE
    freshness_field: str | None = FRESHNESS_FIELD       # last_seen_at_utc
    primary_key_fields: tuple[str, ...] = PRIMARY_KEYS
    default_chunk_size: int = 1000
    supports_incremental: bool = True

    # ── Source column contract ────────────────────────────────────────────────

    def get_source_columns(self) -> tuple[str, ...]:
        """
        Return the explicit ordered source columns for dim_notification_content.

        These columns must stay aligned with NotificationContentRow.from_row().
        Adding or removing a column here requires a matching change in
        the schema row dataclass.

        content_id note:
            VARCHAR(100) with no declared PK constraint. Treated as the stable
            de facto key; used as the ordering tiebreaker.

        sender_user_id note:
            Nullable string FK. NULL for system-generated or anonymous
            notifications. Preserved as NULL; transformer gates sender-edge
            creation on non-NULL values.

        first/last_seen_date_key note:
            INTEGER partition keys in the DWH; coerced to str | None in the
            row dataclass. Extracted as-is; interpretation is a transformer
            concern.
        """
        return (
            "content_id",                   # VARCHAR(100); no PK constraint — de facto key
            "sender_user_id",               # nullable string FK — NULL for system/anonymous
            "normalized_message_text",
            "message_text_sample",
            "first_seen_at_utc",
            "last_seen_at_utc",             # extractor watermark field
            "first_seen_date_key",          # INTEGER partition key in DWH; coerced to str
            "last_seen_date_key",           # INTEGER partition key in DWH; coerced to str
        )

    # ── Query construction ────────────────────────────────────────────────────

    def build_base_query(self) -> str:
        """
        Return the base SELECT for dim_notification_content without
        incremental filtering.

        The incremental clause (WHERE last_seen_at_utc > :watermark_value)
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
        Build the incremental filter using last_seen_at_utc.

        Uses strict greater-than semantics so watermark advancement remains
        monotonic across runs. Covers re-observed deduplicated messages in
        addition to newly created content rows.

        No clause is emitted on first run (watermark is None), triggering a
        full-table bootstrap load.
        """
        if not self.supports_incremental or not self.freshness_field:
            return ""

        if not watermark_value:
            return ""

        return f"\nWHERE {self.freshness_field} > :watermark_value"

    def build_order_by_clause(self) -> str:
        """
        Return stable deterministic ordering for dim_notification_content.

        last_seen_at_utc first — aligns with watermark advancement and
        clusters output by most recent observation of each message.

        content_id second — VARCHAR de facto key; breaks ties within the
        same last_seen_at_utc bucket deterministically. Absence of a declared
        PK constraint does not affect ordering correctness as long as
        content_id values are unique in practice.
        """
        return "\nORDER BY last_seen_at_utc, content_id"

    def build_pagination_clause(self, limit: int, offset: int) -> str:
        """
        Return LIMIT/OFFSET pagination clause.
        """
        return "\nLIMIT %(limit)s OFFSET %(offset)s"