"""
Extractor for the jct_notification_recipients warehouse source.

Purpose:
- Extract notification recipient rows from jct_notification_recipients,
  including notification identity, recipient user, content reference,
  partition date key, send timestamp, and read state.
- Incremental strategy using sent_at_utc as the watermark.
- Return typed NotificationRecipientsRow instances wrapped in ExtractorBatch.

Junction table — RECEIVED_NOTIFICATION relationship source:
    jct_notification_recipients is a junction table. Each row represents one
    delivery event of a notification to a user and maps directly to a
    RECEIVED_NOTIFICATION edge (User → NotificationContent) in the graph,
    carrying sent_at, is_read, and read_at as edge properties.

Composite logical key — (notification_id, user_id):
    No single-column PK is declared in the DWH. The composite key
    (notification_id, user_id) is the stable row identifier. The extractor
    does not deduplicate; deduplication is a transformer concern.

Watermark field — sent_at_utc:
    sent_at_utc is the correct incremental field for this source. Junction
    rows are inserted when a notification is sent and may subsequently be
    mutated when a user reads the notification (is_read flips from 0 to 1,
    read_at_utc is populated). However, sent_at_utc does not advance on
    read events — it is set once at send time.

    This means read-state mutations (is_read, read_at_utc) on rows already
    past the watermark will not be captured by subsequent incremental runs.
    If read-state capture is required incrementally, a secondary watermark
    on read_at_utc or an updated_at_utc field would be needed. This
    extractor follows the declared schema FRESHNESS_FIELD (sent_at_utc)
    as-is; read-state completeness is a pipeline design concern.

    On first run (watermark is None), a full-table bootstrap load captures
    all historical delivery and read state.

Design rules:
- notification_id is the leading composite key field; string type.
- user_id is a nullable string; NULL rows represent unresolved recipients
  and are extracted faithfully. The transformer must handle NULL user_id
  when creating RECEIVED_NOTIFICATION edges.
- is_read is TINYINT 0/1 in the DWH; extracted as int | None, not bool.
- notification_date_key is INTEGER in the DWH; coerced to str | None in
  the row dataclass (YYYYMMDD format assumed).
- No graph logic, edge construction, or property mapping here.

Source schema:
- Source table  : jct_notification_recipients
- Inclusion mode: GRAPH_CORE
- Graph entity  : RECEIVED_NOTIFICATION (User → NotificationContent)
- Freshness field: sent_at_utc
- Declared PK   : none (composite key: notification_id, user_id)
"""

from __future__ import annotations

from app.contracts.warehouse_rows import WarehouseRow
from app.extractors.base import BaseExtractor
from app.schemas.warehouse.notification_recipients import (
    FRESHNESS_FIELD,
    INCLUSION_MODE,
    PRIMARY_KEYS,
    SOURCE_NAME,
    NotificationRecipientsRow,
)


class NotificationRecipientsExtractor(BaseExtractor):
    """
    Extractor for jct_notification_recipients.

    Incremental strategy:
    - watermark field: sent_at_utc
    - ordering: sent_at_utc, notification_id, user_id

    Junction table:
    - One row per (notification_id, user_id) delivery event. Maps to a
      RECEIVED_NOTIFICATION edge (User → NotificationContent) carrying
      sent_at, is_read, and read_at as edge properties.

    Read-state mutation caveat:
    - sent_at_utc does not advance when a user reads a notification.
      Incremental runs will not re-capture is_read / read_at_utc mutations
      on rows already past the watermark. A full-refresh or secondary
      read_at_utc watermark would be required to cover read-state updates
      exhaustively. This extractor follows the declared FRESHNESS_FIELD.

    Nullable user_id:
    - user_id is NULL for unresolved recipients. Extracted faithfully;
      transformer must handle NULL user_id when constructing edges.
    """

    source_name: str = SOURCE_NAME
    schema_row_class: type[WarehouseRow] = NotificationRecipientsRow
    inclusion_mode: str = INCLUSION_MODE
    freshness_field: str | None = FRESHNESS_FIELD       # sent_at_utc
    primary_key_fields: tuple[str, ...] = PRIMARY_KEYS
    default_chunk_size: int = 2000
    supports_incremental: bool = True

    # ── Source column contract ────────────────────────────────────────────────

    def get_source_columns(self) -> tuple[str, ...]:
        """
        Return the explicit ordered source columns for jct_notification_recipients.

        These columns must stay aligned with NotificationRecipientsRow.from_row().
        Adding or removing a column here requires a matching change in
        the schema row dataclass.

        is_read note:
            TINYINT 0/1 in the DWH; coerced to int | None. Not a Python bool.

        notification_date_key note:
            INTEGER partition key in the DWH; coerced to str | None in the
            row dataclass (YYYYMMDD format assumed).

        user_id note:
            Nullable string. NULL for unresolved recipients. Preserved as
            NULL; transformer must handle NULL user_id when constructing
            RECEIVED_NOTIFICATION edges.

        Composite key note:
            No single-column PK declared. (notification_id, user_id) is the
            stable row identifier. Deduplication is a transformer concern.

        Read-state mutation note:
            is_read and read_at_utc may change post-send but sent_at_utc
            does not advance on read events. Read-state mutations on rows
            already past the watermark are not captured incrementally.
        """
        return (
            "notification_id",              # leading composite key field
            "user_id",                      # nullable string — NULL for unresolved recipients
            "content_id",                   # nullable string FK
            "notification_date_key",        # INTEGER partition key in DWH
            "sent_at_utc",                  # extractor watermark field
            "is_read",                      # TINYINT 0/1 in DWH (not bool)
            "read_at_utc",                  # NULL until notification is read
        )

    # ── Query construction ────────────────────────────────────────────────────

    def build_base_query(self) -> str:
        """
        Return the base SELECT for jct_notification_recipients without
        incremental filtering.

        The incremental clause (WHERE sent_at_utc > :watermark_value)
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
        Build the incremental filter using sent_at_utc.

        Uses strict greater-than semantics so watermark advancement remains
        monotonic across runs. Captures newly sent notification delivery
        events since the previous watermark.

        Note: sent_at_utc is fixed at send time. Read-state mutations
        (is_read, read_at_utc) on rows already past the watermark are not
        captured by this clause — see class docstring for details.

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
        Return stable deterministic ordering for jct_notification_recipients.

        sent_at_utc first — aligns with watermark advancement and clusters
        output chronologically by delivery time.

        notification_id second — leading composite key field; groups all
        recipient rows for the same notification together within each
        sent_at_utc bucket.

        user_id third — trailing composite key field; resolves ties within
        the same (sent_at_utc, notification_id) bucket deterministically.
        NULL user_id values sort consistently under MySQL default collation.
        """
        return "\nORDER BY sent_at_utc, notification_id, user_id"

    def build_pagination_clause(self, limit: int, offset: int) -> str:
        """
        Return LIMIT/OFFSET pagination clause.
        """
        return "\nLIMIT %(limit)s OFFSET %(offset)s"