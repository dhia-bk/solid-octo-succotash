"""
Extractor for the fct_retention_cohorts warehouse source.

Purpose:
- Extract cohort retention aggregate rows from fct_retention_cohorts,
  including cohort size, partition date key, cohort date, weeks-since-cohort
  period, period start/end boundaries, active user count, and retention rate.
- Incremental strategy using cohort_date_key as the partition watermark.
- Return typed RetentionCohortsRow instances wrapped in ExtractorBatch.

Non-graph source:
    fct_retention_cohorts is SERVING_ONLY — it feeds cohort retention
    dashboards and emits no graph nodes or edges. The extractor obeys the
    same BaseExtractor contract as graph-emitting sources; INCLUSION_MODE
    carries the routing signal that downstream consumers use to distinguish
    serving-layer rows from graph rows.

No declared PK — composite stable key:
    fct_retention_cohorts has no single-column PK constraint in the DWH.
    The composite key (cohort_date_key, period_weeks_since_cohort) is the
    stable row identifier. PRIMARY_KEYS reflects this composite declaration.
    The extractor does not deduplicate rows — that is a downstream dashboard
    or serving-layer concern.

Watermark field — cohort_date_key (overrides schema FRESHNESS_FIELD):
    The schema declares FRESHNESS_FIELD = "cohort_date" (a DATE column).
    This extractor overrides that declaration in favour of cohort_date_key
    (the INTEGER partition key) for the following reasons:
    - Partition pruning: the DWH query planner can use cohort_date_key to
      skip entire cohort partitions that predate the watermark, avoiding
      full scans on large retention fact tables.
    - Aggregate stability: cohort retention rows for a closed cohort partition
      are immutable once computed. Filtering by the integer partition key
      correctly captures only new cohort windows without re-extracting
      historical rows.
    - cohort_date (DATE column) and cohort_date_key (INTEGER YYYYMMDD key)
      encode the same calendar date. The integer key is strictly preferred
      for partition-aligned filtering on partitioned fact tables.

    cohort_date_key is an INTEGER partition key in the DWH; coerced to
    str | None in the row dataclass. Integer ordering semantics apply in
    the DWH regardless of the Python str coercion.

Design rules:
- cohort_date_key and period_weeks_since_cohort form the composite stable
  key; both are included in PRIMARY_KEYS and ORDER BY.
- cohort_date, period_start, period_end are DATE columns; extracted as
  str | None without datetime coercion (date-only labels, no timezone).
- retention_rate is DECIMAL(5,2) in the DWH; coerced to float | None.
- No graph logic, dashboard logic, or cohort computation is applied here.

Source schema:
- Source table  : fct_retention_cohorts
- Inclusion mode: SERVING_ONLY (non-graph)
- Graph entity  : none
- Freshness field (schema): cohort_date
- Freshness field (extractor): cohort_date_key — see watermark note above
- Declared PK   : none (composite key: cohort_date_key, period_weeks_since_cohort)
"""

from __future__ import annotations

from app.contracts.warehouse_rows import WarehouseRow
from app.extractors.base import BaseExtractor
from app.schemas.warehouse.retention_cohorts import (
    INCLUSION_MODE,
    PRIMARY_KEYS,
    SOURCE_NAME,
    RetentionCohortsRow,
)


_WATERMARK_FIELD: str = "cohort_date_key"


class RetentionCohortsExtractor(BaseExtractor):
    """
    Extractor for fct_retention_cohorts.

    Incremental strategy:
    - watermark field: cohort_date_key (INTEGER partition key; str in row)
    - ordering: cohort_date_key, period_weeks_since_cohort

    Non-graph source:
    - SERVING_ONLY inclusion mode; feeds cohort retention dashboards only.
      No graph nodes or edges are emitted. BaseExtractor contract is obeyed
      identically to graph-emitting sources.

    Partition-aligned watermark:
    - cohort_date_key is the integer partition key for this cohort fact table.
      Filtering on it enables partition pruning and avoids re-extracting
      finalized historical cohort windows. cohort_date (schema FRESHNESS_FIELD)
      is intentionally not used — see module docstring for rationale.

    Composite stable key:
    - No single-column PK exists. The composite key (cohort_date_key,
      period_weeks_since_cohort) is the stable row identifier. The extractor
      preserves all rows as received; deduplication is a downstream concern.
    """

    source_name: str = SOURCE_NAME
    schema_row_class: type[WarehouseRow] = RetentionCohortsRow
    inclusion_mode: str = INCLUSION_MODE
    freshness_field: str | None = _WATERMARK_FIELD      # cohort_date_key
    primary_key_fields: tuple[str, ...] = PRIMARY_KEYS
    default_chunk_size: int = 2000
    supports_incremental: bool = True

    # ── Source column contract ────────────────────────────────────────────────

    def get_source_columns(self) -> tuple[str, ...]:
        """
        Return the explicit ordered source columns for fct_retention_cohorts.

        These columns must stay aligned with RetentionCohortsRow.from_row().
        Adding or removing a column here requires a matching change in
        the schema row dataclass.

        cohort_date_key note:
            INTEGER partition key in the DWH; coerced to str | None in the
            row dataclass. Used as the extractor watermark field (overrides
            schema FRESHNESS_FIELD = cohort_date).

        cohort_date, period_start, period_end note:
            DATE columns in the DWH (YYYY-MM-DD); extracted as str | None.
            No datetime coercion applied — date-only labels, no timezone.

        retention_rate note:
            DECIMAL(5,2) in the DWH; coerced to float | None.

        Composite key note:
            No single-column PK declared. (cohort_date_key,
            period_weeks_since_cohort) is the stable composite identifier.
            Deduplication belongs to downstream consumers.
        """
        return (
            "cohort_size",
            "cohort_date_key",                  # INTEGER partition key; extractor watermark
            "cohort_date",                      # DATE column; str in row; no tz coercion
            "period_weeks_since_cohort",        # part of composite stable key
            "period_start",                     # DATE column; str in row; no tz coercion
            "period_end",                       # DATE column; str in row; no tz coercion
            "active_user_count",
            "retention_rate",                   # DECIMAL(5,2) in DWH
        )

    # ── Query construction ────────────────────────────────────────────────────

    def build_base_query(self) -> str:
        """
        Return the base SELECT for fct_retention_cohorts without incremental
        filtering.

        The incremental clause
        (WHERE cohort_date_key > %(watermark_value)s) is appended by the
        base runtime via build_incremental_clause().
        """
        columns = ",\n    ".join(self.get_source_columns())
        return f"""
SELECT
    {columns}
FROM {self.source_name}
""".strip()

    def build_incremental_clause(self, watermark_value: str | None) -> str:
        """
        Build the incremental filter using cohort_date_key.

        Filters on the integer partition key using strict greater-than
        semantics. Partition pruning allows the DWH query planner to skip
        entire cohort partitions that predate the watermark, making
        incremental runs cheaper on large retention fact tables.

        Closed cohort partitions are immutable once computed; filtering by
        cohort_date_key therefore avoids re-extracting already-processed
        historical cohort windows.

        No clause is emitted on first run (watermark is None), triggering a
        full-table bootstrap load across all historical cohort partitions.
        """
        if not self.supports_incremental or not self.freshness_field:
            return ""

        if not watermark_value:
            return ""

        return f"\nWHERE {self.freshness_field} > %(watermark_value)s"

    def build_order_by_clause(self) -> str:
        """
        Return stable deterministic ordering for fct_retention_cohorts.

        cohort_date_key first — aligns with partition watermark advancement
        and groups output by cohort calendar day, matching the natural
        structure of the cohort fact table.

        period_weeks_since_cohort second — integer; the second component of
        the composite stable key. Breaks ties within the same cohort partition
        deterministically and produces naturally ascending period sequences
        per cohort, which benefits downstream dashboard consumers.
        """
        return "\nORDER BY cohort_date_key, period_weeks_since_cohort"

    def build_pagination_clause(self, limit: int, offset: int) -> str:
        """
        Return LIMIT/OFFSET pagination clause.
        """
        return "\nLIMIT %(limit)s OFFSET %(offset)s"