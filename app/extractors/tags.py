"""
Extractor for the dim_tags warehouse source.

Purpose:
- Extract tag catalog rows from dim_tags, including identity, usage counts,
  trending signals, and optional team/league references.
- Incremental strategy using last_used_at_utc as the watermark.
- Return typed TagsRow instances wrapped in ExtractorBatch.

Watermark field — last_used_at_utc:
    last_used_at_utc is the correct incremental field for this source
    because dim_tags rows mutate as tags are applied to new content:
    - post_usage_count and news_usage_count increment with each tagging event
    - is_trending and trending_score are recomputed as usage patterns shift
    - last_used_at_utc advances with each new tagging event
    Incremental runs therefore capture all tags whose trending state or
    usage counts have changed since the previous run, not just newly created
    tags.

Nullable team/league references:
    team_id and league_id are NULL for non-sport tags. Extracted faithfully
    as NULL; the transformer gates team/league-edge creation on non-NULL
    values.

Design rules:
- tag_id is an integer PK; used as the ordering tiebreaker.
- is_trending is TINYINT 0/1 in the DWH; extracted as int | None, not bool.
- trending_score is DECIMAL(10,2) in the DWH; coerced to float | None.
- No graph logic, canonicalization, or enrichment is applied here.

Source schema:
- Source table  : dim_tags
- Inclusion mode: GRAPH_CORE
- Graph entity  : Tag
- Freshness field: last_used_at_utc
- Declared PK   : tag_id
"""

from __future__ import annotations

from app.contracts.warehouse_rows import WarehouseRow
from app.extractors.base import BaseExtractor
from app.schemas.warehouse.tags import (
    FRESHNESS_FIELD,
    INCLUSION_MODE,
    PRIMARY_KEYS,
    SOURCE_NAME,
    TagsRow,
)


class TagsExtractor(BaseExtractor):
    """
    Extractor for dim_tags.

    Incremental strategy:
    - watermark field: last_used_at_utc
    - ordering: last_used_at_utc, tag_id

    Mutation coverage:
    - last_used_at_utc advances as tags are applied to new content, ensuring
      incremental runs capture tags with updated usage counts or trending
      state, not only newly created tags.

    Nullable team/league references:
    - team_id and league_id are NULL for non-sport tags. Extracted
      faithfully; transformer gates team/league-edge creation on non-NULL
      values.
    """

    source_name: str = SOURCE_NAME
    schema_row_class: type[WarehouseRow] = TagsRow
    inclusion_mode: str = INCLUSION_MODE
    freshness_field: str | None = FRESHNESS_FIELD       # last_used_at_utc
    primary_key_fields: tuple[str, ...] = PRIMARY_KEYS
    default_chunk_size: int = 1000
    supports_incremental: bool = True

    # ── Source column contract ────────────────────────────────────────────────

    def get_source_columns(self) -> tuple[str, ...]:
        """
        Return the explicit ordered source columns for dim_tags.

        These columns must stay aligned with TagsRow.from_row().
        Adding or removing a column here requires a matching change in
        the schema row dataclass.

        is_trending note:
            TINYINT 0/1 in the DWH; coerced to int | None. Not a Python bool.

        trending_score note:
            DECIMAL(10,2) in the DWH; coerced to float | None.

        team_id / league_id note:
            INTEGER; NULL for non-sport tags. Preserved as NULL; transformer
            gates team/league-edge creation on non-NULL values.
        """
        return (
            "tag_id",
            "tag_name",
            "tag_url",
            "post_usage_count",
            "news_usage_count",
            "last_used_at_utc",     # extractor watermark field
            "team_id",              # INTEGER; NULL for non-sport tags
            "league_id",            # INTEGER; NULL for non-sport tags
            "is_trending",          # TINYINT 0/1 in DWH (not bool)
            "trending_score",       # DECIMAL(10,2) in DWH
        )

    # ── Query construction ────────────────────────────────────────────────────

    def build_base_query(self) -> str:
        """
        Return the base SELECT for dim_tags without incremental filtering.

        The incremental clause (WHERE last_used_at_utc > %(watermark_value)s)
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
        Build the incremental filter using last_used_at_utc.

        Uses strict greater-than semantics so watermark advancement remains
        monotonic across runs. Covers usage count and trending signal
        mutations in addition to newly created tags.

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
        Return stable deterministic ordering for dim_tags.

        last_used_at_utc first — aligns with watermark advancement and
        clusters output by most recent tagging activity.

        tag_id second — integer PK; breaks ties within the same
        last_used_at_utc bucket deterministically.
        """
        return "\nORDER BY last_used_at_utc, tag_id"

    def build_pagination_clause(self, limit: int, offset: int) -> str:
        """
        Return LIMIT/OFFSET pagination clause.
        """
        return "\nLIMIT %(limit)s OFFSET %(offset)s"