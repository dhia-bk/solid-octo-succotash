"""
Extractor for the fct_user_notification_stats warehouse source.

Purpose:
- Extract per-user notification engagement aggregate rows from
  fct_user_notification_stats, including receive/read totals, read rate,
  active day counts, consistency score, and last notification timestamp.
- Full-refresh strategy — incremental extraction is not used for this source.
- Return typed UserNotificationStatsRow instances wrapped in ExtractorBatch.

Non-graph source:
    fct_user_notification_stats is FEATURE_SOURCE — it feeds the notification
    feature view in the serving layer only and emits no graph nodes or edges.
    The extractor obeys the same BaseExtractor contract as graph-emitting
    sources; INCLUSION_MODE carries the routing signal that downstream
    consumers use to distinguish feature-pipeline rows from graph rows.

Full-refresh rationale — why not incremental on last_notification_at_utc:
    The schema declares FRESHNESS_FIELD = "last_notification_at_utc". This
    extractor does not use it as an incremental watermark for the following
    reasons:

    1. Aggregate drift: fct_user_notification_stats holds pre-aggregated
       totals (total_received, total_read, read_rate_pct, active_days_*,
       consistency_score). Any notification event — for any user — can shift
       these aggregates. An incremental filter on last_notification_at_utc
       would capture only users who received a notification after the
       watermark, silently missing users whose older notifications were
       subsequently marked as read, whose consistency_score was recomputed,
       or whose aggregates were corrected by a DWH restatement.

    2. No aggregate_updated_at: without a field that advances whenever a
       row's aggregate values change (not just when the last notification
       arrived), there is no safe incremental watermark. Using
       last_notification_at_utc as a proxy would yield stale feature data
       in the serving layer for affected users.

    3. Table volume: fct_user_notification_stats is a per-user aggregate
       (one row per user_id), not a raw event log. Its cardinality is bounded
       by the user base, not notification volume. Full-refresh extraction of a
       user-scoped aggregate table is operationally acceptable and preferable
       to the silent staleness risk of an incorrect incremental filter.

    A periodic full-refresh (e.g. daily or per pipeline run) is the correct
    strategy for this source until the DWH exposes a reliable
    aggregate_updated_at or row_version field.

No declared PK:
    fct_user_notification_stats has no declared PK constraint in the DWH.
    user_id is treated as the stable de facto key. The extractor does not
    deduplicate — that is a downstream concern if duplicate user_id rows
    are detected.

Design rules:
- user_id is a string de facto key; ordering uses string collation.
- read_rate_pct and consistency_score are DECIMAL(5,2) in the DWH; coerced
  to float | None.
- No graph logic, feature engineering, or scoring model logic here.

Source schema:
- Source table  : fct_user_notification_stats
- Inclusion mode: FEATURE_SOURCE (non-graph)
- Graph entity  : none
- Freshness field (schema): last_notification_at_utc
- Freshness field (extractor): none — full refresh; see rationale above
- Declared PK   : none (user_id treated as stable de facto key)
"""

from __future__ import annotations

from app.contracts.warehouse_rows import WarehouseRow
from app.extractors.base import BaseExtractor
from app.schemas.warehouse.user_notification_stats import (
    INCLUSION_MODE,
    PRIMARY_KEYS,
    SOURCE_NAME,
    UserNotificationStatsRow,
)


class UserNotificationStatsExtractor(BaseExtractor):
    """
    Extractor for fct_user_notification_stats.

    Extraction strategy: full refresh.
    - supports_incremental = False
    - freshness_field = None
    - ordering: user_id

    Non-graph source:
    - FEATURE_SOURCE inclusion mode; feeds the notification feature view
      in the serving layer only. No graph nodes or edges are emitted.
      BaseExtractor contract is obeyed identically to graph-emitting sources.

    Full-refresh rationale:
    - fct_user_notification_stats holds pre-aggregated per-user totals.
      Any notification event can shift aggregates for any user. There is no
      aggregate_updated_at field to serve as a reliable incremental watermark.
      last_notification_at_utc (schema FRESHNESS_FIELD) is not a safe proxy —
      it does not advance when read counts, read_rate_pct, active_days_*, or
      consistency_score change without a new notification arriving.
      Full-refresh ensures the feature view always reflects the latest
      recomputed aggregates for all users. See module docstring for details.

    No declared PK:
    - user_id is the de facto stable key. The extractor preserves all rows
      as received; deduplication is a downstream concern.
    """

    source_name: str = SOURCE_NAME
    schema_row_class: type[WarehouseRow] = UserNotificationStatsRow
    inclusion_mode: str = INCLUSION_MODE
    freshness_field: str | None = None                  # full refresh — see module docstring
    primary_key_fields: tuple[str, ...] = PRIMARY_KEYS
    default_chunk_size: int = 2000
    supports_incremental: bool = False

    # ── Source column contract ────────────────────────────────────────────────

    def get_source_columns(self) -> tuple[str, ...]:
        """
        Return the explicit ordered source columns for fct_user_notification_stats.

        These columns must stay aligned with UserNotificationStatsRow.from_row().
        Adding or removing a column here requires a matching change in
        the schema row dataclass.

        read_rate_pct / consistency_score note:
            DECIMAL(5,2) in the DWH; coerced to float | None.

        No-PK note:
            user_id has no declared PK constraint. Treated as the stable de
            facto key; deduplication belongs to downstream consumers.

        Full-refresh note:
            last_notification_at_utc is extracted faithfully as a data column
            but is not used as an incremental watermark. See module docstring.
        """
        return (
            "user_id",                      # de facto stable key; no PK constraint
            "total_received",
            "total_read",
            "read_rate_pct",                # DECIMAL(5,2) in DWH
            "active_days_received",
            "active_days_read",
            "consistency_score",            # DECIMAL(5,2) in DWH
            "last_notification_at_utc",     # data column only — not used as watermark
        )

    # ── Query construction ────────────────────────────────────────────────────

    def build_base_query(self) -> str:
        """
        Return the base SELECT for fct_user_notification_stats.

        No incremental clause is appended — supports_incremental is False
        and freshness_field is None, so build_incremental_clause() returns
        an empty string on every call.
        """
        columns = ",\n    ".join(self.get_source_columns())
        return f"""
SELECT
    {columns}
FROM {self.source_name}
""".strip()

    def build_order_by_clause(self) -> str:
        """
        Return stable deterministic ordering for fct_user_notification_stats.

        user_id only — string de facto key; provides fully deterministic
        ordering across all rows. No secondary tiebreaker is needed because
        user_id is unique in practice (one aggregate row per user).
        """
        return "\nORDER BY user_id"

    def build_pagination_clause(self, limit: int, offset: int) -> str:
        """
        Return LIMIT/OFFSET pagination clause.
        """
        return "\nLIMIT %(limit)s OFFSET %(offset)s"