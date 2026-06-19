"""
Extractor for the dim_teams warehouse source.

Purpose:
- Extract canonical team identity from dim_teams.
- Full-refresh strategy — the source has no freshness/mutation timestamp,
  so every pipeline run extracts all rows deterministically.
- Return typed TeamsRow instances wrapped in ExtractorBatch.

Design rules:
- This extractor is the canonical team identity source.
- team_id is VARCHAR(100) in the DWH and must be kept as a string here.
  Cross-source ID type reconciliation (e.g. against dim_teams_enhanced
  which stores team_id as INTEGER) belongs to the transformer layer.
- No incremental filtering is attempted; supports_incremental is False.
- The manifest is flagged as a full-refresh batch by the base runtime
  because watermark_value will always be None on both entry and exit.
- No graph logic, canonicalization, or enrichment is applied here.

Source schema:
- Source table  : dim_teams
- Inclusion mode: GRAPH_CORE
- Graph entity  : Team
- Freshness field: None (static dimension)
"""

from __future__ import annotations

from app.contracts.warehouse_rows import WarehouseRow
from app.extractors.base import BaseExtractor
from app.schemas.warehouse.teams import (
    FRESHNESS_FIELD,
    INCLUSION_MODE,
    PRIMARY_KEYS,
    SOURCE_NAME,
    TeamsRow,
)


class TeamsExtractor(BaseExtractor):
    """
    Extractor for dim_teams.

    Full-refresh strategy:
    - supports_incremental = False
    - freshness_field      = None
    - watermark is never read or written for this source
    - every run extracts the full team catalog

    Ordering:
    - stable deterministic sort by team_id ensures idempotent output
      across repeated full-refresh runs.
    """

    source_name: str = SOURCE_NAME
    schema_row_class: type[WarehouseRow] = TeamsRow
    inclusion_mode: str = INCLUSION_MODE
    freshness_field: str | None = FRESHNESS_FIELD     # None — static source
    primary_key_fields: tuple[str, ...] = PRIMARY_KEYS
    default_chunk_size: int = 1000                    
    supports_incremental: bool = False

    # ── Source column contract ────────────────────────────────────────────────

    def get_source_columns(self) -> tuple[str, ...]:
        """
        Return the explicit ordered source columns for dim_teams.

        These columns must stay aligned with TeamsRow.from_row().
        Adding or removing a column here requires a matching change in
        the schema row dataclass.
        """
        return (
            "team_id",
            "team_name",
            "team_code",
            "country",
            "venue_name",
            "team_logo",
        )

    # ── Query construction ────────────────────────────────────────────────────

    def build_base_query(self) -> str:
        """
        Return the base SELECT for dim_teams.

        No WHERE clause is included; dim_teams is always fully refreshed.
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

        dim_teams has no freshness timestamp and is never extracted
        incrementally.  This override makes the intent explicit and prevents
        accidental watermark injection if supports_incremental is ever
        toggled during refactoring.
        """
        return ""

    def build_order_by_clause(self) -> str:
        """
        Return stable deterministic ordering for dim_teams.

        Sorting by team_id (VARCHAR) ensures the full-refresh output is
        identical across runs, which simplifies diff-based change detection
        in downstream layers.
        """
        return "\nORDER BY team_id"

    def build_pagination_clause(self, limit: int, offset: int) -> str:
        """
        Return LIMIT/OFFSET pagination clause.
        """
        return "\nLIMIT %(limit)s OFFSET %(offset)s"