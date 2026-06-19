"""
Extractor for the dim_news warehouse source.

Purpose:
- Extract editorial news rows from dim_news, including news_id, title,
  content, publication time, author, media URL, and active state.
- Incremental strategy using published_at_utc as the watermark.
- Return typed NewsRow instances wrapped in ExtractorBatch.

Source characteristics:
    dim_news holds one row per editorial news article. Rows are created
    when an article is published and are generally immutable thereafter.
    is_active can toggle (e.g. article retraction), meaning a row can
    mutate after its published_at_utc — the same limitation seen in
    dim_discussions (is_closed) and dim_posts (engagement counts).

    For most pipeline use cases this is acceptable — editorial news content
    is stable after publication and is_active changes are rare and
    low-frequency. Pipeline operators who need accurate is_active state on
    historical articles should schedule periodic full-refresh runs.

    dim_news relates to dim_ai_articles via published_news_id on the AI
    article side — when an AI article is approved and published, its
    published_news_id references the resulting editorial news record.
    Both news_id (integer PK here) and published_news_id (integer FK on
    dim_ai_articles) must be preserved for the transformer to construct
    the cross-entity linkage.

Design rules:
- news_id is an INTEGER PK; stored as int in NewsRow. Integer sort order
  is naturally correct without CAST.
- is_active is a TINYINT 0/1 flag; stored as int | None. Can change after
  publication; incremental runs will not re-extract is_active changes on
  historical articles.
- content and title may be large free-text fields; extracted faithfully —
  field-length enforcement is a loader concern.
- No graph logic, canonicalization, or enrichment is applied here.

Source schema:
- Source table  : dim_news
- Inclusion mode: GRAPH_CORE
- Graph entity  : News
- Freshness field: published_at_utc
"""

from __future__ import annotations

from app.contracts.warehouse_rows import WarehouseRow
from app.extractors.base import BaseExtractor
from app.schemas.warehouse.news import (
    FRESHNESS_FIELD,
    INCLUSION_MODE,
    PRIMARY_KEYS,
    SOURCE_NAME,
    NewsRow,
)


class NewsExtractor(BaseExtractor):
    """
    Extractor for dim_news.

    Incremental strategy:
    - watermark field: published_at_utc
    - ordering: published_at_utc, news_id

    Active state limitation:
    - is_active can toggle after publication (e.g. article retraction).
      Incremental runs by published_at_utc will not re-extract is_active
      changes on historical articles. Schedule periodic full-refresh runs
      when accurate is_active state on historical news is required.

    AI article linkage:
    - dim_ai_articles.published_news_id references news_id as a FK.
      news_id (integer) is preserved here for that cross-entity linkage
      to be resolved in the transformer layer.
    """

    source_name: str = SOURCE_NAME
    schema_row_class: type[WarehouseRow] = NewsRow
    inclusion_mode: str = INCLUSION_MODE
    freshness_field: str | None = FRESHNESS_FIELD     # published_at_utc
    primary_key_fields: tuple[str, ...] = PRIMARY_KEYS
    default_chunk_size: int = 2000                    
    supports_incremental: bool = True

    # ── Source column contract ────────────────────────────────────────────────

    def get_source_columns(self) -> tuple[str, ...]:
        """
        Return the explicit ordered source columns for dim_news.

        These columns must stay aligned with NewsRow.from_row().
        Adding or removing a column here requires a matching change in
        the schema row dataclass.

        is_active note:
            TINYINT 0/1 flag; can change after publication (retraction).
            Incremental runs will not re-extract is_active changes on
            historical articles — see class docstring.

        Cross-entity linkage note:
            news_id (integer PK) is referenced by dim_ai_articles via
            published_news_id. Preserved as int for that FK resolution.
        """
        return (
            "news_id",
            "title",
            "content",
            "published_at_utc",
            "author",
            "image",
            "url",
            "is_active",    # mutable after publication — see active state note
        )

    # ── Query construction ────────────────────────────────────────────────────

    def build_base_query(self) -> str:
        """
        Return the base SELECT for dim_news without incremental filtering.

        The incremental clause (WHERE published_at_utc > %(watermark_value)s)
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
        Build the incremental filter using published_at_utc.

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
        Return stable deterministic ordering for dim_news.

        published_at_utc first — aligns with watermark advancement and
        clusters output by publication time.

        news_id second — integer PK; breaks ties within the same publication
        timestamp bucket deterministically. Integer sort order is naturally
        correct without CAST.
        """
        return "\nORDER BY published_at_utc, news_id"

    def build_pagination_clause(self, limit: int, offset: int) -> str:
        """
        Return LIMIT/OFFSET pagination clause.
        """
        return "\nLIMIT %(limit)s OFFSET %(offset)s"