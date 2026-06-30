"""
Extractor for the fct_user_sessions warehouse source.

Purpose:
- Extract session aggregate rows from fct_user_sessions, including user
  identity, session start and end timestamps, duration, partition date key,
  session status, page view counts, and landing/exit pages.
- Incremental strategy using session_start_utc as the watermark.
- Return typed UserSessionsRow instances wrapped in ExtractorBatch.

Non-graph source:
    fct_user_sessions is FEATURE_SOURCE — sessions are too transient and
    user-anchored for graph node representation. This source feeds the
    behaviour model feature pipeline only and emits no graph nodes or edges.
    The extractor obeys the same BaseExtractor contract as graph-emitting
    sources; INCLUSION_MODE carries the routing signal that downstream
    consumers use to distinguish feature-pipeline rows from graph rows.

Watermark field — session_start_utc:
    session_start_utc is the correct incremental field because sessions are
    append-only event records — a session begins, is written, and is not
    materially mutated post-creation. New sessions always carry a
    session_start_utc beyond the previous watermark, ensuring incremental
    runs capture all newly recorded sessions without rescanning historical
    rows.

    Note: session_end_utc and session_duration_seconds may be backfilled
    after session_start_utc is written (e.g. for sessions recorded as
    in-progress). If those backfills do not advance session_start_utc,
    incremental runs will miss them. This extractor follows session_start_utc
    as declared in the schema; if backfill coverage is required, an
    updated_at_utc field should be added to the schema.

Nullable user field:
    user_id is NULL for anonymous or unauthenticated sessions. Extracted
    faithfully as NULL; feature pipeline consumers must handle anonymous
    sessions appropriately (e.g. exclusion or separate bucketing).

Design rules:
- session_id is the declared PK; used as the ordering tiebreaker.
- session_date_key is INTEGER in the DWH (YYYYMMDD partition key); coerced
  to str | None in the row dataclass — a partition label, not a quantity.
- landing_page and exit_page may be free-text URL strings; extracted
  faithfully — length enforcement is a loader concern.
- No feature engineering, ML model logic, or graph logic applied here.

Source schema:
- Source table  : fct_user_sessions
- Inclusion mode: FEATURE_SOURCE (non-graph)
- Graph entity  : none
- Freshness field: session_start_utc
- Declared PK   : session_id
"""

from __future__ import annotations

from app.contracts.warehouse_rows import WarehouseRow
from app.extractors.base import BaseExtractor
from app.schemas.warehouse.user_sessions import (
    FRESHNESS_FIELD,
    INCLUSION_MODE,
    PRIMARY_KEYS,
    SOURCE_NAME,
    UserSessionsRow,
)


class UserSessionsExtractor(BaseExtractor):
    """
    Extractor for fct_user_sessions.

    Incremental strategy:
    - watermark field: session_start_utc
    - ordering: session_start_utc, session_id

    Append-dominant source:
    - fct_user_sessions is a session event log; rows are appended on session
      creation. session_start_utc reliably captures all new sessions in
      incremental runs.

    Session end backfill caveat:
    - session_end_utc and session_duration_seconds may be backfilled post-
      creation for in-progress sessions. Those backfills will not be captured
      incrementally if session_start_utc is not advanced. See module docstring.

    Nullable user field:
    - user_id is NULL for anonymous or unauthenticated sessions. Extracted
      faithfully; feature pipeline consumers must handle anonymous sessions.
    """

    source_name: str = SOURCE_NAME
    schema_row_class: type[WarehouseRow] = UserSessionsRow
    inclusion_mode: str = INCLUSION_MODE
    freshness_field: str | None = FRESHNESS_FIELD       # session_start_utc
    primary_key_fields: tuple[str, ...] = PRIMARY_KEYS
    default_chunk_size: int = 2000
    supports_incremental: bool = True

    # ── Source column contract ────────────────────────────────────────────────

    def get_source_columns(self) -> tuple[str, ...]:
        """
        Return the explicit ordered source columns for fct_user_sessions.

        These columns must stay aligned with UserSessionsRow.from_row().
        Adding or removing a column here requires a matching change in
        the schema row dataclass.

        session_date_key note:
            INTEGER in the DWH (YYYYMMDD partition key); coerced to str | None
            in the row dataclass. A partition label, not a quantity.

        user_id note:
            NULL for anonymous or unauthenticated sessions. Preserved as NULL;
            feature pipeline consumers must handle anonymous sessions.

        landing_page / exit_page note:
            Free-text URL strings of variable length. Extracted faithfully;
            field-length enforcement is a loader concern.
        """
        return (
            "session_id",
            "user_id",                      # NULL for anonymous sessions
            "session_start_utc",            # extractor watermark field
            "session_end_utc",
            "session_duration_seconds",
            "session_date_key",             # INTEGER partition key in DWH; str in row
            "session_status",
            "page_views",
            "distinct_page_views",
            "landing_page",                 # free-text URL; variable length
            "exit_page",                    # free-text URL; variable length
        )

    # ── Query construction ────────────────────────────────────────────────────

    def build_base_query(self) -> str:
        """
        Return the base SELECT for fct_user_sessions without incremental
        filtering.

        The incremental clause (WHERE session_start_utc > :watermark_value)
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
        Build the incremental filter using session_start_utc.

        Uses strict greater-than semantics so watermark advancement remains
        monotonic across runs. Appropriate for an append-dominant session log
        where rows are created at session start and not materially mutated
        post-creation in the common case.

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
        Return stable deterministic ordering for fct_user_sessions.

        session_start_utc first — aligns with watermark advancement and
        clusters output chronologically by session creation time.

        session_id second — declared PK; breaks ties within the same
        session_start_utc bucket deterministically.
        """
        return "\nORDER BY session_start_utc, session_id"

    def build_pagination_clause(self, limit: int, offset: int) -> str:
        """
        Return LIMIT/OFFSET pagination clause.
        """
        return "\nLIMIT %(limit)s OFFSET %(offset)s"