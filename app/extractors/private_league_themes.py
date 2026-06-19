"""
Extractor for the dim_private_league_themes warehouse source.

Purpose:
- Extract visual theme rows from dim_private_league_themes, including
  theme and league identity, color palette fields, banner URL, and default
  icon.
- Full-refresh strategy: FRESHNESS_FIELD is None; all rows are extracted on
  every run. No incremental filtering is applied.
- Return typed PrivateLeagueThemesRow instances wrapped in ExtractorBatch.

Full-refresh rationale:
    dim_private_league_themes is a static visual configuration dimension.
    Theme records change infrequently (color palette updates, new banners),
    and no updated_at or equivalent mutation timestamp exists in the DWH.
    Full refresh on every run is the correct strategy: the table is small,
    the cost of a full scan is negligible, and it guarantees the graph
    always reflects the current theme state without stale enrichment risk.

No declared PK — unstable theme_id:
    dim_private_league_themes has no declared PK constraint in the DWH.
    theme_id is INTEGER but is not guaranteed to be unique. The schema
    docstring explicitly notes that the transformer should use
    private_league_id as the de facto stable merge key for graph operations
    until a proper unique constraint is added. Both theme_id and
    private_league_id are extracted faithfully so the transformer can apply
    its fallback merge-key logic without re-querying the source.

    Extractor ordering uses private_league_id as the primary sort key and
    theme_id as the secondary key, reflecting private_league_id's role as
    the stable de facto identifier.

Nullable theme_id:
    theme_id is int | None in the row dataclass — it may be NULL in the DWH
    for rows without a valid theme assignment. The transformer must handle
    NULL theme_id gracefully and fall back to private_league_id for graph
    merge key resolution.

Design rules:
- FRESHNESS_FIELD is None; supports_incremental is False. build_incremental_
  clause() always returns an empty string.
- Both private_league_id and theme_id are extracted and preserved; the
  transformer owns merge-key fallback logic.
- All color fields and banner_url are TEXT in the DWH; extracted as str | None.
- No graph logic, theme merging, or property canonicalization here.

Source schema:
- Source table  : dim_private_league_themes
- Inclusion mode: GRAPH_ENRICHMENT
- Graph entity  : LeagueTheme
- Freshness field: None (static; full refresh every run)
- Declared PK   : none (theme_id not unique; private_league_id is de facto
                  stable merge key)
"""

from __future__ import annotations

from app.contracts.warehouse_rows import WarehouseRow
from app.extractors.base import BaseExtractor
from app.schemas.warehouse.private_league_themes import (
    FRESHNESS_FIELD,
    INCLUSION_MODE,
    PRIMARY_KEYS,
    SOURCE_NAME,
    PrivateLeagueThemesRow,
)


class PrivateLeagueThemesExtractor(BaseExtractor):
    """
    Extractor for dim_private_league_themes.

    Full-refresh strategy:
    - FRESHNESS_FIELD is None; supports_incremental is False.
    - All rows are extracted on every run; no watermark filtering is applied.
    - ordering: private_league_id, theme_id

    Static dimension:
    - dim_private_league_themes is a visual configuration catalog with no
      mutation timestamp. Full refresh guarantees current theme state without
      stale enrichment risk. The table is expected to be small; full-scan
      cost is negligible.

    Unstable theme_id:
    - theme_id has no declared unique constraint in the DWH and may be NULL.
      private_league_id is the de facto stable merge key. Both are extracted
      faithfully; the transformer owns merge-key fallback logic.
    """

    source_name: str = SOURCE_NAME
    schema_row_class: type[WarehouseRow] = PrivateLeagueThemesRow
    inclusion_mode: str = INCLUSION_MODE
    freshness_field: str | None = FRESHNESS_FIELD       # None — static source
    primary_key_fields: tuple[str, ...] = PRIMARY_KEYS
    default_chunk_size: int = 1000
    supports_incremental: bool = False

    # ── Source column contract ────────────────────────────────────────────────

    def get_source_columns(self) -> tuple[str, ...]:
        """
        Return the explicit ordered source columns for dim_private_league_themes.

        These columns must stay aligned with PrivateLeagueThemesRow.from_row().
        Adding or removing a column here requires a matching change in
        the schema row dataclass.

        theme_id note:
            INTEGER in the DWH but has no declared unique constraint; may be
            NULL. Not a reliable sole merge key — transformer must fall back
            to private_league_id when theme_id is NULL or not unique.

        private_league_id note:
            INTEGER; the de facto stable merge key for graph operations until
            a unique constraint is added to theme_id. Always extracted and
            preserved alongside theme_id for transformer fallback logic.

        Color field notes:
            background_color, primary_text_color, accent_color,
            secondary_text_color, card_background_color — TEXT in DWH;
            extracted as str | None.

        banner_url / default_icon:
            TEXT in DWH; extracted as str | None.
        """
        return (
            "theme_id",                     # INTEGER; no unique constraint; may be NULL
            "private_league_id",            # INTEGER; de facto stable merge key
            "background_color",             # TEXT in DWH
            "primary_text_color",           # TEXT in DWH
            "accent_color",                 # TEXT in DWH
            "secondary_text_color",         # TEXT in DWH
            "card_background_color",        # TEXT in DWH
            "banner_url",                   # TEXT in DWH
            "default_icon",                 # TEXT in DWH
        )

    # ── Query construction ────────────────────────────────────────────────────

    def build_base_query(self) -> str:
        """
        Return the base SELECT for dim_private_league_themes.

        No incremental clause is appended — this is a full-refresh source.
        All rows are returned on every run.
        """
        columns = ",\n    ".join(self.get_source_columns())
        return f"""
SELECT
    {columns}
FROM {self.source_name}
""".strip()

    def build_incremental_clause(self, watermark_value: str | None) -> str:
        """
        Always returns an empty string — full-refresh source.

        dim_private_league_themes has no freshness field and does not support
        incremental extraction. This override is explicit to document intent;
        the base class default would also return an empty string when
        supports_incremental is False.
        """
        return ""

    def build_order_by_clause(self) -> str:
        """
        Return stable deterministic ordering for dim_private_league_themes.

        private_league_id first — the de facto stable merge key; primary sort
        reflects its role as the reliable row identifier over the unconstrained
        theme_id. Grouping by private_league_id first also surfaces any
        duplicate theme_id values within the same league for easier detection.

        theme_id second — INTEGER; breaks ties within the same private_league_id
        deterministically. NULL theme_id values sort first under MySQL default
        collation (NULLS FIRST), which is consistent across full-refresh runs.
        """
        return "\nORDER BY private_league_id, theme_id"

    def build_pagination_clause(self, limit: int, offset: int) -> str:
        """
        Return LIMIT/OFFSET pagination clause.
        """
        return "\nLIMIT %(limit)s OFFSET %(offset)s"