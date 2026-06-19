"""
Extractor for the dim_teams_enhanced warehouse source.

Purpose:
- Extract team fan analytics enrichment from dim_teams_enhanced.
- Full-refresh strategy — although the source declares last_fan_joined_at as
  a freshness field, fan aggregate columns (fan_percentage, fan_rank,
  fan_engagement_score, fan_growth_rate) are recomputed across all teams on
  each warehouse run. A partial incremental extraction would produce stale
  rank and aggregate values for teams not touched since the last watermark.
  Full refresh is therefore the correct and safe strategy for this source.
- Return typed TeamsEnhancedRow instances wrapped in ExtractorBatch.

Design rules:
- team_id is INTEGER in dim_teams_enhanced (unlike dim_teams where it is
  VARCHAR). This extractor must preserve the source integer exactly.
  Cross-source ID reconciliation (string vs integer team_id) belongs to the
  transformer/mapping layer, not here.
- league_id is a FK to dim_leagues. Preservation is required; resolution
  belongs to the transformer layer.
- No incremental filtering is attempted; supports_incremental is False.
- No graph logic, canonicalization, or enrichment is applied here.

Source schema:
- Source table  : dim_teams_enhanced
- Inclusion mode: GRAPH_ENRICHMENT
- Graph entity  : Team (enrichment only — does not create a new node type)
- Freshness field: last_fan_joined_at (declared but not used for watermarking;
                   full-refresh semantics override incremental filtering)
"""

from __future__ import annotations

from app.contracts.warehouse_rows import WarehouseRow
from app.extractors.base import BaseExtractor
from app.schemas.warehouse.teams_enhanced import (
    FRESHNESS_FIELD,
    INCLUSION_MODE,
    PRIMARY_KEYS,
    SOURCE_NAME,
    TeamsEnhancedRow,
)


class TeamsEnhancedExtractor(BaseExtractor):
    """
    Extractor for dim_teams_enhanced.

    Full-refresh strategy:
    - supports_incremental = False
    - watermark is never read or written for this source
    - every run extracts the full fan analytics enrichment catalog

    Rationale for full refresh over incremental:
        Fan aggregate columns — fan_percentage, fan_rank, fan_engagement_score,
        fan_growth_rate, active_fans_last_30d, fan_retention_rate — are
        recomputed globally on each warehouse refresh cycle. Incrementing by
        last_fan_joined_at would silently omit teams whose aggregate values
        changed without a new fan joining (e.g. rank shifts caused by another
        team's fan growth). Full refresh is the only correct extraction
        strategy for a table with inter-row ranking semantics.

    Ordering:
    - stable deterministic sort by team_id (integer) ensures idempotent output
      across repeated full-refresh runs.
    """

    source_name: str = SOURCE_NAME
    schema_row_class: type[WarehouseRow] = TeamsEnhancedRow
    inclusion_mode: str = INCLUSION_MODE
    freshness_field: str | None = FRESHNESS_FIELD     
    primary_key_fields: tuple[str, ...] = PRIMARY_KEYS
    default_chunk_size: int = 1000
    supports_incremental: bool = False

    # ── Source column contract ────────────────────────────────────────────────

    def get_source_columns(self) -> tuple[str, ...]:
        """
        Return the explicit ordered source columns for dim_teams_enhanced.

        These columns must stay aligned with TeamsEnhancedRow.from_row().
        Adding or removing a column here requires a matching change in
        the schema row dataclass.

        Preservation note:
            league_id is included exactly as sourced. Even though it is a FK
            that requires transformer-layer resolution before graph writes,
            the extractor must not drop or resolve it.

        Integer team_id note:
            team_id is selected as-is. The DWH stores it as INTEGER here
            (unlike dim_teams where it is VARCHAR). No coercion is applied
            in SQL; TeamsEnhancedRow.from_row() handles Python-level typing.
        """
        return (
            "team_id",
            "team_name",
            "team_logo",
            "league_id",
            "country",
            "total_fans",
            "fan_percentage",
            "fan_rank",
            "top_fan_country",
            "top_fan_gender",
            "avg_fan_age",
            "total_predictions_for_team",
            "total_predictions_by_fans",
            "fan_engagement_score",
            "active_fans_last_30d",
            "fan_retention_rate",
            "first_fan_joined_at",
            "last_fan_joined_at",
            "new_fans_last_30d",
            "fan_growth_rate",
        )

    # ── Query construction ────────────────────────────────────────────────────

    def build_base_query(self) -> str:
        """
        Return the base SELECT for dim_teams_enhanced.

        No WHERE clause is included; dim_teams_enhanced is always fully
        refreshed because its aggregate and ranking columns are globally
        recomputed on every warehouse run.
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

        dim_teams_enhanced uses full-refresh semantics. Although
        last_fan_joined_at is declared as a freshness field in the schema
        module, filtering by it would produce incorrect fan rank and aggregate
        values for teams not touched since the last watermark. This override
        makes the no-incremental intent explicit and protects against
        accidental watermark injection during future refactoring.
        """
        return ""

    def build_order_by_clause(self) -> str:
        """
        Return stable deterministic ordering for dim_teams_enhanced.

        team_id is INTEGER here; numeric sort order is therefore naturally
        correct without any CAST. Sorting consistently across full-refresh
        runs enables diff-based change detection in downstream layers.
        """
        return "\nORDER BY team_id"

    def build_pagination_clause(self, limit: int, offset: int) -> str:
        """
        Return LIMIT/OFFSET pagination clause.
        """
        return "\nLIMIT %(limit)s OFFSET %(offset)s"