"""
Extractor for the fct_notification_content_daily warehouse source.

Purpose:
- Extract daily delivery aggregate rows from fct_notification_content_daily,
  including content identity, partition date key, recipient and read counts,
  read rate, and send timestamps.
- Incremental strategy using notification_date_key as the partition watermark.
- Return typed NotificationContentDailyRow instances wrapped in ExtractorBatch.

Non-graph source:
    fct_notification_content_daily is FEATURE_SOURCE — it feeds the
    notification scoring model only and emits no graph nodes or edges.
    The extractor obeys the same BaseExtractor contract as graph-emitting
    sources; INCLUSION_MODE carries the routing signal that downstream
    consumers use to distinguish feature-pipeline rows from graph rows.

No declared PK:
    fct_notification_content_daily has no declared PK constraint in the DWH.
    content_day_id is treated as the stable de facto key. The extractor does
    not attempt to deduplicate rows — that is a transformer or feature-pipeline
    concern if duplicates are detected.

Watermark field — notification_date_key (overrides schema FRESHNESS_FIELD):
    The schema declares FRESHNESS_FIELD = "first_sent_at_utc". This extractor
    overrides that declaration in favour of notification_date_key because
    fct_notification_content_daily is a daily partitioned fact table. Each
    distinct notification_date_key value represents one calendar day of
    delivery aggregates. Filtering on the integer partition key is both
    semantically correct and query-efficient:
    - Partition pruning: the DWH query planner can use notification_date_key
      to skip entire date partitions that predate the watermark.
    - Aggregate stability: daily aggregates for a completed date partition are
      immutable once the partition is closed. Filtering by date key therefore
      correctly captures only new or in-progress partitions.
    - first_sent_at_utc advances within a partition as content items are sent
      throughout the day; using it as the watermark would re-extract rows from
      the same partition multiple times as the day progresses, producing
      duplicate delivery in the feature pipeline.

    notification_date_key is an INTEGER partition key in the DWH, stored as
    str | None in the row dataclass (coerced via str()). The watermark
    comparison uses integer-string ordering, which is monotonically correct
    for YYYYMMDD-formatted date keys with consistent zero-padding.

    Bootstrap note: on first run (watermark is None), no clause is emitted
    and a full-table load is performed, capturing all historical partitions.

Ordering — notification_date_key, content_id:
    notification_date_key first — aligns with partition watermark advancement
    and groups rows by calendar day, matching the natural fact table structure.
    content_id second — nullable string FK; provides deterministic tiebreaking
    within each date partition. NULL content_id values sort first under
    default MySQL collation; this is consistent across runs.

Design rules:
- content_day_id has no declared PK constraint; treated as the stable de
  facto key. Deduplication is a downstream concern.
- notification_date_key is INTEGER in the DWH; coerced to str | None in
  the row dataclass (YYYYMMDD format assumed).
- read_rate_pct is DECIMAL(5,2) in the DWH; coerced to float | None.
- No graph logic, scoring model logic, or feature engineering here.

Source schema:
- Source table  : fct_notification_content_daily
- Inclusion mode: FEATURE_SOURCE (non-graph)
- Graph entity  : none
- Freshness field (schema): first_sent_at_utc
- Freshness field (extractor): notification_date_key — see watermark note above
- Declared PK   : none (content_day_id treated as stable de facto key)
"""

from __future__ import annotations

from app.contracts.warehouse_rows import WarehouseRow
from app.extractors.base import BaseExtractor
from app.schemas.warehouse.notification_content_daily import (
    INCLUSION_MODE,
    PRIMARY_KEYS,
    SOURCE_NAME,
    NotificationContentDailyRow,
)

# Override the schema's declared FRESHNESS_FIELD (first_sent_at_utc) with
# the integer partition key for partition-aligned incremental extraction.
# See module docstring for full rationale.
_WATERMARK_FIELD: str = "notification_date_key"


class NotificationContentDailyExtractor(BaseExtractor):
    """
    Extractor for fct_notification_content_daily.

    Incremental strategy:
    - watermark field: notification_date_key (INTEGER partition key; str in row)
    - ordering: notification_date_key, content_id

    Non-graph source:
    - FEATURE_SOURCE inclusion mode; feeds notification scoring model only.
      No graph nodes or edges are emitted. BaseExtractor contract is obeyed
      identically to graph-emitting sources.

    Partition-aligned watermark:
    - notification_date_key is the integer partition key for this daily fact
      table. Filtering on it enables partition pruning and avoids
      re-extracting rows from completed, immutable date partitions.
      first_sent_at_utc (schema FRESHNESS_FIELD) is intentionally not used
      as the watermark — see module docstring for rationale.

    No declared PK:
    - content_day_id is the de facto stable key. The extractor preserves all
      rows as received; deduplication is a downstream concern.
    """

    source_name: str = SOURCE_NAME
    schema_row_class: type[WarehouseRow] = NotificationContentDailyRow
    inclusion_mode: str = INCLUSION_MODE
    freshness_field: str | None = _WATERMARK_FIELD      # notification_date_key
    primary_key_fields: tuple[str, ...] = PRIMARY_KEYS
    default_chunk_size: int = 2000
    supports_incremental: bool = True

    # ── Source column contract ────────────────────────────────────────────────

    def get_source_columns(self) -> tuple[str, ...]:
        """
        Return the explicit ordered source columns for fct_notification_content_daily.

        These columns must stay aligned with NotificationContentDailyRow.from_row().
        Adding or removing a column here requires a matching change in
        the schema row dataclass.

        notification_date_key note:
            INTEGER partition key in the DWH; coerced to str | None in the
            row dataclass. Used as the extractor watermark field (overrides
            schema FRESHNESS_FIELD = first_sent_at_utc).

        read_rate_pct note:
            DECIMAL(5,2) in the DWH; coerced to float | None.

        No-PK note:
            content_day_id has no declared PK constraint. Treated as the
            stable de facto key; deduplication belongs to downstream consumers.
        """
        return (
            "content_day_id",               # de facto stable key; no PK constraint
            "content_id",                   # nullable string FK
            "notification_date_key",        # INTEGER partition key; extractor watermark
            "recipient_count",
            "read_count",
            "read_rate_pct",                # DECIMAL(5,2) in DWH
            "first_sent_at_utc",
            "last_sent_at_utc",
        )

    # ── Query construction ────────────────────────────────────────────────────

    def build_base_query(self) -> str:
        """
        Return the base SELECT for fct_notification_content_daily without
        incremental filtering.

        The incremental clause
        (WHERE notification_date_key > :watermark_value) is appended by
        the base runtime via build_incremental_clause().
        """
        columns = ",\n    ".join(self.get_source_columns())
        return f"""
SELECT
    {columns}
FROM {self.source_name}
""".strip()

    def build_incremental_clause(self, watermark_value: str | None) -> str:
        """
        Build the incremental filter using notification_date_key.

        Filters on the integer partition key using strict greater-than
        semantics. Partition pruning allows the DWH query planner to skip
        entire date partitions that predate the watermark, making incremental
        runs significantly cheaper than timestamp-based filtering on a large
        fact table.

        Completed date partitions are immutable; filtering by date key
        therefore avoids re-extracting already-processed historical rows.

        No clause is emitted on first run (watermark is None), triggering a
        full-table bootstrap load across all historical partitions.
        """
        if not self.supports_incremental or not self.freshness_field:
            return ""

        if not watermark_value:
            return ""

        return f"\nWHERE {self.freshness_field} > :watermark_value"

    def build_order_by_clause(self) -> str:
        """
        Return stable deterministic ordering for fct_notification_content_daily.

        notification_date_key first — aligns with partition watermark
        advancement and groups output by calendar day, matching the natural
        structure of the daily fact table.

        content_id second — nullable string FK; provides deterministic
        tiebreaking within each date partition. NULL content_id values sort
        consistently under MySQL default collation across runs.
        """
        return "\nORDER BY notification_date_key, content_id"

    def build_pagination_clause(self, limit: int, offset: int) -> str:
        """
        Return LIMIT/OFFSET pagination clause.
        """
        return "\nLIMIT %(limit)s OFFSET %(offset)s"