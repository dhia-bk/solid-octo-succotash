"""
Extractor for the fct_content_engagement_daily warehouse source.

Purpose:
- Extract daily content engagement rollup rows from
  fct_content_engagement_daily, including content identity, metric date,
  partition date key, and daily engagement counters (likes, comments, tags,
  team/league mentions, total engagement).
- Incremental strategy using metric_date as the date-partition watermark.
- Return typed ContentEngagementDailyRow instances wrapped in ExtractorBatch.

Non-graph source:
    fct_content_engagement_daily is SERVING_ONLY — it feeds content
    engagement dashboards and emits no graph nodes or edges. The extractor
    obeys the same BaseExtractor contract as graph-emitting sources;
    INCLUSION_MODE carries the routing signal that downstream consumers use
    to distinguish serving-layer rows from graph rows.

No declared PK:
    fct_content_engagement_daily has no declared PK constraint in the DWH.
    engagement_id is VARCHAR(100) and is treated as the stable de facto key.
    The extractor does not deduplicate rows — that is a downstream dashboard
    or serving-layer concern.

Watermark field — metric_date:
    metric_date is a DATE column in the DWH (date-only; no time component,
    no timezone coercion), stored as str | None in the row dataclass.
    It is the correct incremental field because:
    - Daily rollup rows are keyed by calendar date; metric_date advances
      monotonically as new days are computed.
    - Filtering on metric_date aligns with the natural partition boundary of
      the daily fact table, avoiding re-extraction of historical completed
      days.
    - Daily engagement aggregates for a closed date are immutable once the
      day's rollup is finalized; strict greater-than filtering correctly
      captures only new or in-progress date partitions.

    String comparison semantics: metric_date is a DATE column and will be
    returned from the DWH as a date-formatted string (YYYY-MM-DD). Strict
    greater-than comparison on ISO date strings is monotonically correct.

Design rules:
- engagement_id is VARCHAR(100) with no declared PK constraint; treated as
  the stable de facto key. Deduplication is a downstream concern.
- content_id is INTEGER in the DWH (not str as spec suggested); extracted
  as int | None.
- metric_date is a DATE column (no time component); extracted as str | None
  without datetime coercion. No warehouse_value_to_utc_datetime call needed.
- metric_date_key is an INTEGER partition key; coerced to str | None.
- No graph logic, dashboard logic, or aggregation is applied here.

Source schema:
- Source table  : fct_content_engagement_daily
- Inclusion mode: SERVING_ONLY (non-graph)
- Graph entity  : none
- Freshness field: metric_date
- Declared PK   : none (engagement_id treated as stable de facto key)
"""

from __future__ import annotations

from app.contracts.warehouse_rows import WarehouseRow
from app.extractors.base import BaseExtractor
from app.schemas.warehouse.content_engagement_daily import (
    FRESHNESS_FIELD,
    INCLUSION_MODE,
    PRIMARY_KEYS,
    SOURCE_NAME,
    ContentEngagementDailyRow,
)


class ContentEngagementDailyExtractor(BaseExtractor):
    """
    Extractor for fct_content_engagement_daily.

    Incremental strategy:
    - watermark field: metric_date (DATE column; str in row; YYYY-MM-DD)
    - ordering: metric_date, engagement_id

    Non-graph source:
    - SERVING_ONLY inclusion mode; feeds content engagement dashboards only.
      No graph nodes or edges are emitted. BaseExtractor contract is obeyed
      identically to graph-emitting sources.

    Date-partition watermark:
    - metric_date is a DATE column representing the rollup calendar day.
      Filtering on it avoids re-extracting finalized historical day partitions.
      String ISO date comparison (YYYY-MM-DD) is monotonically correct.

    No declared PK:
    - engagement_id is the de facto stable key. The extractor preserves all
      rows as received; deduplication is a downstream concern.
    """

    source_name: str = SOURCE_NAME
    schema_row_class: type[WarehouseRow] = ContentEngagementDailyRow
    inclusion_mode: str = INCLUSION_MODE
    freshness_field: str | None = FRESHNESS_FIELD       # metric_date
    primary_key_fields: tuple[str, ...] = PRIMARY_KEYS
    default_chunk_size: int = 2000
    supports_incremental: bool = True

    # ── Source column contract ────────────────────────────────────────────────

    def get_source_columns(self) -> tuple[str, ...]:
        """
        Return the explicit ordered source columns for fct_content_engagement_daily.

        These columns must stay aligned with ContentEngagementDailyRow.from_row().
        Adding or removing a column here requires a matching change in
        the schema row dataclass.

        metric_date note:
            DATE column in the DWH (YYYY-MM-DD); extracted as str | None.
            No datetime coercion applied — date-only label, no timezone.
            Used as the extractor watermark field.

        metric_date_key note:
            INTEGER partition key in the DWH; coerced to str | None.

        content_id note:
            INTEGER in the DWH (not str as spec suggested); coerced to
            int | None.

        No-PK note:
            engagement_id is VARCHAR(100) with no declared PK constraint.
            Treated as the stable de facto key; deduplication belongs to
            downstream consumers.
        """
        return (
            "engagement_id",                # VARCHAR(100); de facto stable key; no PK constraint
            "content_type",
            "content_id",                   # INTEGER in DWH (not str)
            "metric_date",                  # DATE column; extractor watermark field
            "metric_date_key",              # INTEGER partition key in DWH
            "likes_today",
            "comments_today",
            "tag_count",
            "team_mention_count",
            "league_mention_count",
            "total_engagement_today",
        )

    # ── Query construction ────────────────────────────────────────────────────

    def build_base_query(self) -> str:
        """
        Return the base SELECT for fct_content_engagement_daily without
        incremental filtering.

        The incremental clause (WHERE metric_date > :watermark_value)
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
        Build the incremental filter using metric_date.

        Filters on the DATE column using strict greater-than semantics.
        ISO date string comparison (YYYY-MM-DD) is monotonically correct.
        Completed daily rollup partitions are immutable, so filtering by
        metric_date avoids re-extracting already-processed historical rows.

        No clause is emitted on first run (watermark is None), triggering a
        full-table bootstrap load across all historical date partitions.
        """
        if not self.supports_incremental or not self.freshness_field:
            return ""

        if not watermark_value:
            return ""

        return f"\nWHERE {self.freshness_field} > :watermark_value"

    def build_order_by_clause(self) -> str:
        """
        Return stable deterministic ordering for fct_content_engagement_daily.

        metric_date first — aligns with watermark advancement and groups
        output by calendar day, matching the natural daily rollup structure.

        engagement_id second — VARCHAR(100) de facto stable key; breaks ties
        within the same metric_date bucket deterministically.
        """
        return "\nORDER BY metric_date, engagement_id"

    def build_pagination_clause(self, limit: int, offset: int) -> str:
        """
        Return LIMIT/OFFSET pagination clause.
        """
        return "\nLIMIT %(limit)s OFFSET %(offset)s"