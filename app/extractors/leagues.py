"""
Extractor for the dim_leagues warehouse source.

Purpose:
- Extract canonical league identity from dim_leagues.
- Low-frequency incremental strategy using updated_at as the watermark.
  The league catalog changes rarely (new seasons, logo updates, active-state
  toggles), so incremental extraction is appropriate and avoids re-processing
  the full catalog on every run.
- Return typed LeaguesRow instances wrapped in ExtractorBatch.

Design rules:
- league_id is INTEGER in dim_leagues. TeamsEnhancedRow also holds an integer
  league_id FK; the transformer is responsible for resolving that FK against
  these rows when writing graph edges.
- Ordering is by league_id (not updated_at first) because the league catalog
  is small and low-churn. PK-ordered output simplifies downstream diff-based
  change detection without the instability of a timestamp-first sort on a
  low-frequency source.
- No graph logic, canonicalization, or enrichment is applied here.

Source schema:
- Source table  : dim_leagues
- Inclusion mode: GRAPH_CORE
- Graph entity  : League
- Freshness field: updated_at
"""

from __future__ import annotations

from app.contracts.warehouse_rows import WarehouseRow
from app.extractors.base import BaseExtractor
from app.schemas.warehouse.leagues import (
    FRESHNESS_FIELD,
    INCLUSION_MODE,
    PRIMARY_KEYS,
    SOURCE_NAME,
    LeaguesRow,
)


class LeaguesExtractor(BaseExtractor):
    """
    Extractor for dim_leagues.

    Incremental strategy:
    - watermark field: updated_at
    - ordering: league_id (PK-stable; catalog is small and low-churn)

    Full-refresh fallback:
    - When no prior watermark exists (first run or checkpoint reset),
      the base runtime omits the incremental clause and extracts all rows.
      This is the correct bootstrap behavior for a catalog source.
    """

    source_name: str = SOURCE_NAME
    schema_row_class: type[WarehouseRow] = LeaguesRow
    inclusion_mode: str = INCLUSION_MODE
    freshness_field: str | None = FRESHNESS_FIELD     # updated_at
    primary_key_fields: tuple[str, ...] = PRIMARY_KEYS
    default_chunk_size: int = 500                     
    supports_incremental: bool = True

    # ── Source column contract ────────────────────────────────────────────────

    def get_source_columns(self) -> tuple[str, ...]:
        """
        Return the explicit ordered source columns for dim_leagues.

        These columns must stay aligned with LeaguesRow.from_row().
        Adding or removing a column here requires a matching change in
        the schema row dataclass.

        season note:
            DWH stores INTEGER; LeaguesRow.from_row() casts to str | None
            because season values are labels ("2024"), not quantities.

        is_active note:
            TINYINT (0/1) in the DWH; kept as int | None per project
            convention — not coerced to bool at the schema layer.
        """
        return (
            "league_id",
            "league_name",
            "country",
            "country_code",
            "country_flag",
            "season",
            "league_logo",
            "is_active",
            "created_at",
            "updated_at",
        )

    # ── Query construction ────────────────────────────────────────────────────

    def build_base_query(self) -> str:
        """
        Return the base SELECT for dim_leagues without incremental filtering.

        The incremental clause (WHERE updated_at > :watermark_value) is
        appended by the base runtime via build_incremental_clause().
        """
        columns = ",\n    ".join(self.get_source_columns())
        return f"""
SELECT
    {columns}
FROM {self.source_name}
""".strip()

    def build_incremental_clause(self, watermark_value: str | None) -> str:
        """
        Build the incremental filter using updated_at.

        Uses strict greater-than semantics so watermark advancement remains
        monotonic across runs. No clause is emitted when:
        - supports_incremental is False (safety guard)
        - watermark_value is None (first run / full-refresh bootstrap)
        """
        if not self.supports_incremental or not self.freshness_field:
            return ""

        if not watermark_value:
            return ""

        return f"\nWHERE {self.freshness_field} > :watermark_value"

    def build_order_by_clause(self) -> str:
        """
        Return stable deterministic ordering for dim_leagues.

        Ordered by league_id (integer PK) rather than updated_at first.
        Rationale:
        - The league catalog is small and low-frequency; timestamp-first
          ordering offers no meaningful chunking benefit.
        - PK-ordered output is stable across full-refresh bootstrap runs
          and simplifies diff-based change detection in downstream layers.
        - Incremental batches will contain only recently updated rows,
          so PK ordering within those small batches is trivially fast.
        """
        return "\nORDER BY league_id"

    def build_pagination_clause(self, limit: int, offset: int) -> str:
        """
        Return LIMIT/OFFSET pagination clause.
        """
        return "\nLIMIT %(limit)s OFFSET %(offset)s"