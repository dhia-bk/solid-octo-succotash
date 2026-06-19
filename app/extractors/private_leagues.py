"""
Extractor for the dim_private_leagues warehouse source.

Purpose:
- Extract private league identity and summary fields from dim_private_leagues.
- Full-refresh strategy — the source has no freshness/mutation timestamp,
  so every pipeline run extracts all rows deterministically.
- Return typed PrivateLeaguesRow instances wrapped in ExtractorBatch.

Design rules:
- private_league_id is INTEGER in the DWH. PrivateLeaguesRow stores it as
  int; no string coercion is applied here.
- owner_user_id is a FK to dim_users (string-typed user_id). Preserved
  exactly as sourced; FK resolution belongs to the transformer layer.
- join_code is a sensitive operational field (allows anyone who knows it
  to join the league). It is extracted faithfully from source truth but
  must not be surfaced in graph DTO contracts or API responses.
- No incremental filtering is attempted; supports_incremental is False.
- No graph logic, canonicalization, or enrichment is applied here.

Source schema:
- Source table  : dim_private_leagues
- Inclusion mode: GRAPH_CORE
- Graph entity  : PrivateLeague
- Freshness field: None (no timestamp column in DWH)
"""

from __future__ import annotations

from app.contracts.warehouse_rows import WarehouseRow
from app.extractors.base import BaseExtractor
from app.schemas.warehouse.private_leagues import (
    FRESHNESS_FIELD,
    INCLUSION_MODE,
    PRIMARY_KEYS,
    SOURCE_NAME,
    PrivateLeaguesRow,
)


class PrivateLeaguesExtractor(BaseExtractor):
    """
    Extractor for dim_private_leagues.

    Full-refresh strategy:
    - supports_incremental = False
    - freshness_field      = None
    - watermark is never read or written for this source
    - every run extracts the full private league catalog

    Ordering:
    - stable deterministic sort by private_league_id (integer PK) ensures
      idempotent output across repeated full-refresh runs and simplifies
      diff-based change detection in downstream layers.
    """

    source_name: str = SOURCE_NAME
    schema_row_class: type[WarehouseRow] = PrivateLeaguesRow
    inclusion_mode: str = INCLUSION_MODE
    freshness_field: str | None = FRESHNESS_FIELD     # None — static source
    primary_key_fields: tuple[str, ...] = PRIMARY_KEYS
    default_chunk_size: int = 2000                    
    supports_incremental: bool = False

    # ── Source column contract ────────────────────────────────────────────────

    def get_source_columns(self) -> tuple[str, ...]:
        """
        Return the explicit ordered source columns for dim_private_leagues.

        These columns must stay aligned with PrivateLeaguesRow.from_row().
        Adding or removing a column here requires a matching change in
        the schema row dataclass.

        Sensitivity note:
            join_code is included because it exists in source truth and
            downstream stages need it for membership validation logic.
            It must not propagate beyond the extraction/transformation
            boundary into graph DTOs or API response contracts.

        FK note:
            owner_user_id is a string FK to dim_users. Preserved as-is;
            resolution and ownership graph edge construction belong to the
            transformer layer.
        """
        return (
            "private_league_id",
            "owner_user_id",
            "league_name",
            "image",
            "about",
            "member_count",
            "join_code",      # sensitive — must not reach graph/API boundary
            "is_generic",
        )

    # ── Query construction ────────────────────────────────────────────────────

    def build_base_query(self) -> str:
        """
        Return the base SELECT for dim_private_leagues.

        No WHERE clause is included; dim_private_leagues is always fully
        refreshed because the source has no mutation timestamp.
        """
        columns = ",\n    ".join(self.get_source_columns())
        return f"""
SELECT
    {columns}
FROM {self.source_name}
""".strip()

    def build_incremental_clause(self, watermark_value: str | None) -> str:
        """
        Always returns an empty string.

        dim_private_leagues has no freshness timestamp and is never extracted
        incrementally. This override makes the intent explicit and prevents
        accidental watermark injection if supports_incremental is ever
        toggled during refactoring.
        """
        return ""

    def build_order_by_clause(self) -> str:
        """
        Return stable deterministic ordering for dim_private_leagues.

        Sorted by private_league_id (integer PK). Integer sort order is
        naturally correct without CAST. Consistent PK ordering across all
        full-refresh runs enables reliable diff-based change detection
        downstream.
        """
        return "\nORDER BY private_league_id"

    def build_pagination_clause(self, limit: int, offset: int) -> str:
        """
        Return LIMIT/OFFSET pagination clause.
        """
        return "\nLIMIT %(limit)s OFFSET %(offset)s"