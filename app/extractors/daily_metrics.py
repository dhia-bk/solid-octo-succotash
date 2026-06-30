"""
Extractor for the fct_daily_metrics warehouse source.

Purpose:
- Extract platform-level daily aggregate KPI rows from fct_daily_metrics,
  including user activity, engagement, subscription, revenue, retention,
  and day-over-day delta metrics.
- Incremental strategy using metric_date as the watermark.
- Return typed DailyMetricsRow instances wrapped in ExtractorBatch.

Non-graph source:
    fct_daily_metrics is SERVING_ONLY — consumed directly by operational
    dashboards without graph intermediation. No graph nodes or edges are
    emitted. The extractor obeys the same BaseExtractor contract as
    graph-emitting sources; INCLUSION_MODE carries the routing signal that
    downstream consumers use to distinguish dashboard-serving rows from
    graph rows.

Watermark field — metric_date:
    metric_date is both the declared PK and the schema FRESHNESS_FIELD for
    this source. It is a DATE column in the DWH, stored as a date-only string
    (YYYY-MM-DD) with no timezone component. Using metric_date as the
    incremental watermark is correct because:
    - Each row represents one complete calendar day of platform-level KPIs.
    - A new row is appended for each new calendar day; historical rows may
      be restated (recalculated_at_utc advances), but metric_date itself
      does not change for a completed day.
    - Strict greater-than filtering on metric_date captures all newly
      appended day rows since the previous run.

    Restatement caveat: if historical metric_date rows are restated (e.g.
    a corrected MRR figure for a past date), those corrections will not be
    captured by incremental runs because metric_date does not advance for
    restated rows. A periodic full-refresh run is recommended as a
    restatement recovery mechanism. For dashboard use cases, recency of
    new-day rows is the primary concern and incremental-on-metric_date
    is appropriate.

    metric_date is stored as str in the row dataclass (DATE column coerced
    via normalize_string_id). Lexicographic string comparison on YYYY-MM-DD
    is monotonically correct.

Design rules:
- metric_date is the PK and ordering field; no tiebreaker is needed.
- All DECIMAL columns are coerced to float | None.
- calculated_at_utc is a DATETIME column; normalized to datetime | None.
- No graph logic, dashboard rendering logic, or KPI computation here.

Source schema:
- Source table  : fct_daily_metrics
- Inclusion mode: SERVING_ONLY (non-graph)
- Graph entity  : none
- Freshness field: metric_date
- Declared PK   : metric_date
"""

from __future__ import annotations

from app.contracts.warehouse_rows import WarehouseRow
from app.extractors.base import BaseExtractor
from app.schemas.warehouse.daily_metrics import (
    FRESHNESS_FIELD,
    INCLUSION_MODE,
    PRIMARY_KEYS,
    SOURCE_NAME,
    DailyMetricsRow,
)


class DailyMetricsExtractor(BaseExtractor):
    """
    Extractor for fct_daily_metrics.

    Incremental strategy:
    - watermark field: metric_date (DATE column; YYYY-MM-DD string)
    - ordering: metric_date

    Serving-only source:
    - SERVING_ONLY inclusion mode; feeds operational dashboards directly.
      No graph nodes or edges are emitted. BaseExtractor contract is obeyed
      identically to graph-emitting sources.

    Append-dominant with restatement caveat:
    - New rows are appended daily. Incremental runs on metric_date correctly
      capture new calendar days. Historical restatements (recalculated MRR,
      corrected retention figures, etc.) are not captured incrementally —
      a periodic full-refresh is recommended as a restatement recovery path.

    Single-column PK / ordering:
    - metric_date is both the declared PK and the sole ORDER BY field.
      One row per calendar day; no tiebreaker is required.
    """

    source_name: str = SOURCE_NAME
    schema_row_class: type[WarehouseRow] = DailyMetricsRow
    inclusion_mode: str = INCLUSION_MODE
    freshness_field: str | None = FRESHNESS_FIELD       # metric_date
    primary_key_fields: tuple[str, ...] = PRIMARY_KEYS
    default_chunk_size: int = 365                       # daily rows; one year per chunk
    supports_incremental: bool = True

    # ── Source column contract ────────────────────────────────────────────────

    def get_source_columns(self) -> tuple[str, ...]:
        """
        Return the explicit ordered source columns for fct_daily_metrics.

        These columns must stay aligned with DailyMetricsRow.from_row().
        Adding or removing a column here requires a matching change in
        the schema row dataclass.

        metric_date note:
            DATE column in the DWH; coerced to str (YYYY-MM-DD) via
            normalize_string_id. Used as both the PK and the incremental
            watermark field. Lexicographic comparison is monotonically correct.

        DECIMAL columns (all coerced to float | None):
            dau_mau_ratio, avg_predictions_per_active_user,
            avg_posts_per_active_user, engagement_rate, mrr, arr,
            churn_rate, mrr_change_vs_yesterday, revenue_new,
            revenue_renewal, payments_volume, retention_rate_day1,
            retention_rate_day7, retention_rate_day30.

        calculated_at_utc note:
            DATETIME column; normalized to datetime | None via
            warehouse_value_to_utc_datetime. Not used as watermark.
        """
        return (
            "metric_date",                          # DATE PK; extractor watermark field
            "total_users",
            "new_signups",
            "active_users_today",
            "active_users_7d",
            "active_users_30d",
            "dau_mau_ratio",                        # DECIMAL
            "total_predictions_today",
            "total_posts_today",
            "total_comments_today",
            "total_quiz_attempts_today",
            "avg_predictions_per_active_user",      # DECIMAL
            "avg_posts_per_active_user",            # DECIMAL
            "engagement_rate",                      # DECIMAL
            "new_subscriptions_today",
            "active_subscriptions",
            "churned_subscriptions_today",
            "mrr",                                  # DECIMAL
            "arr",                                  # DECIMAL
            "churn_rate",                           # DECIMAL
            "signups_change_vs_yesterday",
            "dau_change_vs_yesterday",
            "mrr_change_vs_yesterday",              # DECIMAL
            "calculated_at_utc",                    # DATETIME; not used as watermark
            "active_chat_users",
            "active_session_users",
            "revenue_new",                          # DECIMAL
            "revenue_renewal",                      # DECIMAL
            "payments_volume",                      # DECIMAL
            "active_users_7d_weekly",
            "wau_change_vs_last_week",
            "returning_users_today",
            "retention_rate_day1",                  # DECIMAL
            "retention_rate_day7",                  # DECIMAL
            "retention_rate_day30",                 # DECIMAL
            "wau",
            "returning_users_7d",
            "returning_users_30d",
        )

    # ── Query construction ────────────────────────────────────────────────────

    def build_base_query(self) -> str:
        """
        Return the base SELECT for fct_daily_metrics without incremental
        filtering.

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

        Uses strict greater-than semantics on the YYYY-MM-DD date string.
        Lexicographic ordering on ISO date strings is monotonically correct,
        so string comparison produces the same result as DATE comparison.

        Captures newly appended calendar-day rows since the previous run.
        Does not capture restatements of historical metric_date rows — see
        module docstring for the restatement caveat and recovery guidance.

        No clause is emitted on first run (watermark is None), triggering a
        full-table bootstrap load across all historical daily rows.
        """
        if not self.supports_incremental or not self.freshness_field:
            return ""

        if not watermark_value:
            return ""

        return f"\nWHERE {self.freshness_field} > :watermark_value"

    def build_order_by_clause(self) -> str:
        """
        Return stable deterministic ordering for fct_daily_metrics.

        metric_date only — DATE PK with one row per calendar day; fully
        deterministic without a secondary tiebreaker.
        """
        return "\nORDER BY metric_date"

    def build_pagination_clause(self, limit: int, offset: int) -> str:
        """
        Return LIMIT/OFFSET pagination clause.
        """
        return "\nLIMIT %(limit)s OFFSET %(offset)s"