"""
Extractor for the fct_team_daily_growth warehouse source.

Purpose:
- Extract team-level fan growth time series rows from fct_team_daily_growth,
  including team identity, new/lost/net fan counts, total fans, growth rate,
  partition date key, and calculation timestamp.
- Incremental strategy using metric_date as the date-partition watermark.
- Return typed TeamDailyGrowthRow instances wrapped in ExtractorBatch.

Non-graph source:
    fct_team_daily_growth is FEATURE_SOURCE — it feeds team analytics model
    features and emits no graph nodes or edges. The extractor obeys the same
    BaseExtractor contract as graph-emitting sources; INCLUSION_MODE carries
    the routing signal that downstream consumers use to distinguish feature-
    pipeline rows from graph rows.

No declared PK — composite stable key:
    fct_team_daily_growth has no single-column PK constraint in the DWH.
    The composite key (metric_date, team_id) is the stable row identifier,
    matching the PRIMARY_KEYS declaration in the schema. The extractor does
    not deduplicate rows — that is a downstream feature-pipeline concern.

Watermark field — metric_date:
    metric_date is a DATE column in the DWH (date-only; no time component,
    no timezone coercion), stored as str | None in the row dataclass. It is
    the correct incremental field and matches the schema FRESHNESS_FIELD
    declaration because:
    - Daily growth rows are keyed by calendar date; metric_date advances
      monotonically as new days are computed.
    - Filtering on metric_date aligns with the natural partition boundary of
      the daily fact table, avoiding re-extraction of finalized historical
      days.
    - Daily fan growth aggregates for a closed date are immutable once the
      day's rollup is finalized; strict greater-than filtering correctly
      captures only new or in-progress date partitions.

    String comparison semantics: metric_date is a DATE column and will be
    returned from the DWH as a date-formatted string (YYYY-MM-DD). Strict
    greater-than comparison on ISO date strings is monotonically correct.

Design rules:
- metric_date and team_id form the composite stable key; both are included
  in PRIMARY_KEYS and ORDER BY.
- team_id is VARCHAR(100) in the DWH (not int as spec suggested); extracted
  as str | None.
- metric_date is a DATE column (no time component); extracted as str | None
  without datetime coercion. No warehouse_value_to_utc_datetime call needed.
- metric_date_key is an INTEGER partition key; coerced to str | None.
- growth_rate_pct is DECIMAL(5,2) in the DWH; coerced to float | None.
- calculated_at_utc is a proper datetime; normalized via
  warehouse_value_to_utc_datetime.
- No graph logic, feature engineering, or model logic is applied here.

Source schema:
- Source table  : fct_team_daily_growth
- Inclusion mode: FEATURE_SOURCE (non-graph)
- Graph entity  : none
- Freshness field: metric_date
- Declared PK   : none (composite key: metric_date, team_id)
"""

from __future__ import annotations

from app.contracts.warehouse_rows import WarehouseRow
from app.extractors.base import BaseExtractor
from app.schemas.warehouse.team_daily_growth import (
    FRESHNESS_FIELD,
    INCLUSION_MODE,
    PRIMARY_KEYS,
    SOURCE_NAME,
    TeamDailyGrowthRow,
)


class TeamDailyGrowthExtractor(BaseExtractor):
    """
    Extractor for fct_team_daily_growth.

    Incremental strategy:
    - watermark field: metric_date (DATE column; str in row; YYYY-MM-DD)
    - ordering: metric_date, team_id

    Non-graph source:
    - FEATURE_SOURCE inclusion mode; feeds team analytics model features only.
      No graph nodes or edges are emitted. BaseExtractor contract is obeyed
      identically to graph-emitting sources.

    Date-partition watermark:
    - metric_date is a DATE column representing the growth calendar day.
      Filtering on it avoids re-extracting finalized historical day partitions.
      ISO date string comparison (YYYY-MM-DD) is monotonically correct.

    Composite stable key:
    - No single-column PK exists. The composite key (metric_date, team_id)
      is the stable row identifier. The extractor preserves all rows as
      received; deduplication is a downstream concern.
    """

    source_name: str = SOURCE_NAME
    schema_row_class: type[WarehouseRow] = TeamDailyGrowthRow
    inclusion_mode: str = INCLUSION_MODE
    freshness_field: str | None = FRESHNESS_FIELD       # metric_date
    primary_key_fields: tuple[str, ...] = PRIMARY_KEYS
    default_chunk_size: int = 2000
    supports_incremental: bool = True

    # ── Source column contract ────────────────────────────────────────────────

    def get_source_columns(self) -> tuple[str, ...]:
        """
        Return the explicit ordered source columns for fct_team_daily_growth.

        These columns must stay aligned with TeamDailyGrowthRow.from_row().
        Adding or removing a column here requires a matching change in
        the schema row dataclass.

        metric_date note:
            DATE column in the DWH (YYYY-MM-DD); extracted as str | None.
            No datetime coercion applied — date-only label, no timezone.
            Used as the extractor watermark field.

        team_id note:
            VARCHAR(100) in the DWH (not int as spec suggested); extracted
            as str | None.

        metric_date_key note:
            INTEGER partition key in the DWH; coerced to str | None.

        growth_rate_pct note:
            DECIMAL(5,2) in the DWH; coerced to float | None.

        calculated_at_utc note:
            Proper datetime column; normalized via
            warehouse_value_to_utc_datetime in the row dataclass.

        Composite key note:
            No single-column PK declared. (metric_date, team_id) is the
            stable composite identifier. Deduplication belongs to downstream
            consumers.
        """
        return (
            "metric_date",              # DATE column; extractor watermark field; no tz coercion
            "team_id",                  # VARCHAR(100) in DWH (not int); part of composite key
            "team_name",
            "new_fans_today",
            "total_fans",
            "fans_lost_today",
            "net_fan_change",
            "growth_rate_pct",          # DECIMAL(5,2) in DWH
            "metric_date_key",          # INTEGER partition key in DWH
            "calculated_at_utc",
        )

    # ── Query construction ────────────────────────────────────────────────────

    def build_base_query(self) -> str:
        """
        Return the base SELECT for fct_team_daily_growth without incremental
        filtering.

        The incremental clause (WHERE metric_date > %(watermark_value)s)
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
        Completed daily growth partitions are immutable once finalized, so
        filtering by metric_date avoids re-extracting already-processed
        historical rows.

        No clause is emitted on first run (watermark is None), triggering a
        full-table bootstrap load across all historical date partitions.
        """
        if not self.supports_incremental or not self.freshness_field:
            return ""

        if not watermark_value:
            return ""

        return f"\nWHERE {self.freshness_field} > %(watermark_value)s"

    def build_order_by_clause(self) -> str:
        """
        Return stable deterministic ordering for fct_team_daily_growth.

        metric_date first — aligns with watermark advancement and groups
        output by calendar day, matching the natural daily time series
        structure and the first component of the composite stable key.

        team_id second — VARCHAR(100) stable key; the second component of
        the composite (metric_date, team_id) identifier. Breaks ties within
        the same metric_date bucket deterministically and produces a
        consistent team sequence per day, which benefits downstream feature
        model consumers.
        """
        return "\nORDER BY metric_date, team_id"

    def build_pagination_clause(self, limit: int, offset: int) -> str:
        """
        Return LIMIT/OFFSET pagination clause.
        """
        return "\nLIMIT %(limit)s OFFSET %(offset)s"