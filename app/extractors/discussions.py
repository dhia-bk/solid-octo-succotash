"""
Extractor for the dim_discussions warehouse source.

Purpose:
- Extract fixture-linked discussion thread identity from dim_discussions,
  including discussion_id, fixture_id, creation time, and closure state.
- Incremental strategy using created_at_utc as the watermark.
- Return typed DiscussionsRow instances wrapped in ExtractorBatch.

Source characteristics:
    dim_discussions is a small, low-churn identity table. Each row represents
    a single discussion thread anchored to a fixture (match). Threads are
    created when a fixture's discussion is opened and closed (is_closed = 1)
    after the fixture result window passes.

    is_closed can transition from 0 to 1 after the thread's created_at_utc,
    meaning a row's state can change without its creation timestamp advancing.
    Incremental extraction by created_at_utc therefore captures new threads
    correctly but will miss closure state updates on existing threads.

    For most pipeline use cases this is acceptable — the initial load captures
    all threads, new threads are picked up incrementally, and closure state
    is a low-frequency update that does not require real-time propagation.
    Pipeline operators who need accurate closure state on historical threads
    should schedule periodic full-refresh runs for this source.

Design rules:
- discussion_id is an INTEGER PK; stored as int in DiscussionsRow.
- fixture_id is VARCHAR(255) in the DWH; preserved as str | None to remain
  consistent with dim_fixtures.fixture_id (also VARCHAR). No SQL CAST applied.
- is_closed is a TINYINT 0/1 flag; stored as int | None per project convention.
- No graph logic, canonicalization, or enrichment is applied here.

Source schema:
- Source table  : dim_discussions
- Inclusion mode: GRAPH_CORE
- Graph entity  : Discussion
- Freshness field: created_at_utc
"""

from __future__ import annotations

from app.contracts.warehouse_rows import WarehouseRow
from app.extractors.base import BaseExtractor
from app.schemas.warehouse.discussions import (
    FRESHNESS_FIELD,
    INCLUSION_MODE,
    PRIMARY_KEYS,
    SOURCE_NAME,
    DiscussionsRow,
)


class DiscussionsExtractor(BaseExtractor):
    """
    Extractor for dim_discussions.

    Incremental strategy:
    - watermark field: created_at_utc
    - ordering: created_at_utc, discussion_id

    Closure state limitation:
    - is_closed transitions from 0 to 1 after thread creation. Incremental
      runs by created_at_utc will not re-extract threads whose only change
      is a closure state update. Schedule periodic full-refresh runs when
      accurate is_closed state on historical threads is required.
    """

    source_name: str = SOURCE_NAME
    schema_row_class: type[WarehouseRow] = DiscussionsRow
    inclusion_mode: str = INCLUSION_MODE
    freshness_field: str | None = FRESHNESS_FIELD     # created_at_utc
    primary_key_fields: tuple[str, ...] = PRIMARY_KEYS
    default_chunk_size: int = 2000                    # low-churn identity
                                                      # table; small chunks
                                                      # are sufficient
    supports_incremental: bool = True

    # ── Source column contract ────────────────────────────────────────────────

    def get_source_columns(self) -> tuple[str, ...]:
        """
        Return the explicit ordered source columns for dim_discussions.

        These columns must stay aligned with DiscussionsRow.from_row().
        Adding or removing a column here requires a matching change in
        the schema row dataclass.

        fixture_id type note:
            VARCHAR(255) in the DWH; preserved as str | None — consistent
            with dim_fixtures.fixture_id. Do not apply a SQL CAST to INT.

        is_closed note:
            TINYINT 0/1 flag. Can change from 0 to 1 after the thread's
            created_at_utc; see class docstring for implications on
            incremental extraction completeness.
        """
        return (
            "discussion_id",
            "fixture_id",     # VARCHAR in DWH — preserved as str | None
            "created_at_utc",
            "is_closed",      # mutable after creation — see closure state note
        )

    # ── Query construction ────────────────────────────────────────────────────

    def build_base_query(self) -> str:
        """
        Return the base SELECT for dim_discussions without incremental
        filtering.

        The incremental clause (WHERE created_at_utc > %(watermark_value)s)
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
        Build the incremental filter using created_at_utc.

        Uses strict greater-than semantics so watermark advancement remains
        monotonic across runs. No clause is emitted on first run (watermark
        is None), triggering a full-table bootstrap load.
        """
        if not self.supports_incremental or not self.freshness_field:
            return ""

        if not watermark_value:
            return ""

        return f"\nWHERE {self.freshness_field} > %(watermark_value)s"

    def build_order_by_clause(self) -> str:
        """
        Return stable deterministic ordering for dim_discussions.

        created_at_utc first — aligns with watermark advancement and clusters
        output by thread creation time.

        discussion_id second — integer PK; breaks ties within the same
        creation timestamp bucket deterministically. Integer sort order is
        naturally correct without CAST.
        """
        return "\nORDER BY created_at_utc, discussion_id"

    def build_pagination_clause(self, limit: int, offset: int) -> str:
        """
        Return LIMIT/OFFSET pagination clause.
        """
        return "\nLIMIT %(limit)s OFFSET %(offset)s"