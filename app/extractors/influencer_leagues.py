"""
Extractor for the dim_influencer_leagues warehouse source.

Purpose:
- Extract influencer league rows from dim_influencer_leagues, including
  league identity, name, description, and creation/update timestamps.
- Incremental strategy using updated_at as the watermark.
- Return typed InfluencerLeaguesRow instances wrapped in ExtractorBatch.

Watermark field — updated_at:
    updated_at is the correct incremental field because influencer league
    rows mutate when name or description are edited. updated_at advances on
    each mutation, ensuring incremental runs capture both newly created
    leagues and updated existing leagues. created_at would miss post-creation
    mutations.

Design rules:
- influencer_league_id is an INTEGER PK; used as the ordering tiebreaker.
- created_at and updated_at are TIMESTAMP columns in the DWH; normalized to
  datetime | None via warehouse_value_to_utc_datetime.
- No graph logic, canonicalization, or enrichment is applied here.

Source schema:
- Source table  : dim_influencer_leagues
- Inclusion mode: GRAPH_CORE
- Graph entity  : InfluencerLeague
- Freshness field: updated_at
- Declared PK   : influencer_league_id (INTEGER)
"""

from __future__ import annotations

from app.contracts.warehouse_rows import WarehouseRow
from app.extractors.base import BaseExtractor
from app.schemas.warehouse.influencer_leagues import (
    FRESHNESS_FIELD,
    INCLUSION_MODE,
    PRIMARY_KEYS,
    SOURCE_NAME,
    InfluencerLeaguesRow,
)


class InfluencerLeaguesExtractor(BaseExtractor):
    """
    Extractor for dim_influencer_leagues.

    Incremental strategy:
    - watermark field: updated_at
    - ordering: updated_at, influencer_league_id

    Mutation coverage:
    - updated_at advances on name/description edits, ensuring incremental
      runs capture both new leagues and updated existing ones.
    """

    source_name: str = SOURCE_NAME
    schema_row_class: type[WarehouseRow] = InfluencerLeaguesRow
    inclusion_mode: str = INCLUSION_MODE
    freshness_field: str | None = FRESHNESS_FIELD       # updated_at
    primary_key_fields: tuple[str, ...] = PRIMARY_KEYS
    default_chunk_size: int = 1000
    supports_incremental: bool = True

    # ── Source column contract ────────────────────────────────────────────────

    def get_source_columns(self) -> tuple[str, ...]:
        """
        Return the explicit ordered source columns for dim_influencer_leagues.

        These columns must stay aligned with InfluencerLeaguesRow.from_row().
        Adding or removing a column here requires a matching change in
        the schema row dataclass.

        created_at / updated_at note:
            TIMESTAMP columns in the DWH; normalized to datetime | None via
            warehouse_value_to_utc_datetime.
        """
        return (
            "influencer_league_id",
            "name",
            "description",
            "created_at",
            "updated_at",               # extractor watermark field
        )

    # ── Query construction ────────────────────────────────────────────────────

    def build_base_query(self) -> str:
        """
        Return the base SELECT for dim_influencer_leagues without incremental
        filtering.

        The incremental clause (WHERE updated_at > %(watermark_value)s) is
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
        monotonic across runs. Covers both newly created leagues and leagues
        with mutated name or description.

        No clause is emitted on first run (watermark is None), triggering a
        full-table bootstrap load.
        """
        if not self.supports_incremental or not self.freshness_field:
            return ""

        if not watermark_value:
            return ""

        return f"\nWHERE {self.freshness_field} > %(watermark_value)s"

    def build_order_by_clause(self) -> str:
        """
        Return stable deterministic ordering for dim_influencer_leagues.

        updated_at first — aligns with watermark advancement and clusters
        output by most recent mutation.

        influencer_league_id second — integer PK; breaks ties within the
        same updated_at bucket deterministically.
        """
        return "\nORDER BY updated_at, influencer_league_id"

    def build_pagination_clause(self, limit: int, offset: int) -> str:
        """
        Return LIMIT/OFFSET pagination clause.
        """
        return "\nLIMIT %(limit)s OFFSET %(offset)s"