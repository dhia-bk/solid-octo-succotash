"""
Extractor for the dim_posts warehouse source.

Purpose:
- Extract user-generated post content from dim_posts, including author,
  title, body/content, media URLs, publication timestamp, reaction counts,
  and active state.
- Incremental strategy using published_at_utc as the watermark.
- Return typed PostsRow instances wrapped in ExtractorBatch.

Source characteristics:
    dim_posts holds one row per post. Reaction counts (like_count, clap_count,
    fire_count, football_count, thumbs_up_count, thumbs_down_count) and
    view_count are updated in-place as user engagement accumulates, meaning
    rows can mutate after the original published_at_utc timestamp.

    Filtering by published_at_utc therefore captures new posts correctly on
    incremental runs but will miss engagement count updates on older posts.
    This is an accepted tradeoff for this source: post content and authorship
    are immutable after publication; engagement metrics are refreshed via
    dedicated engagement aggregate sources (fct_content_engagement_daily).

    Pipeline operators who need real-time engagement counts on existing posts
    should use the engagement daily aggregate extractor, not a full-refresh
    of dim_posts.

Design rules:
- post_id is VARCHAR(100) in the DWH; preserved as str. Consistent with
  how post_id is referenced as a FK in dim_comments.
- author_user_id is a string FK to dim_users; preserved as-is.
- content, description, and title may be large free-text fields; extracted
  faithfully — field-length enforcement is a loader concern, not extractor.
- No graph logic, canonicalization, or enrichment is applied here.

Source schema:
- Source table  : dim_posts
- Inclusion mode: GRAPH_CORE
- Graph entity  : Post
- Freshness field: published_at_utc
"""

from __future__ import annotations

from app.contracts.warehouse_rows import WarehouseRow
from app.extractors.base import BaseExtractor
from app.schemas.warehouse.posts import (
    FRESHNESS_FIELD,
    INCLUSION_MODE,
    PRIMARY_KEYS,
    SOURCE_NAME,
    PostsRow,
)


class PostsExtractor(BaseExtractor):
    """
    Extractor for dim_posts.

    Incremental strategy:
    - watermark field: published_at_utc
    - ordering: published_at_utc, post_id

    Engagement count limitation:
    - Reaction and view counts mutate after publication. Incremental runs
      by published_at_utc capture new posts only; engagement count updates
      on existing posts are not re-extracted. Use fct_content_engagement_daily
      for up-to-date engagement aggregates on historical posts.
    """

    source_name: str = SOURCE_NAME
    schema_row_class: type[WarehouseRow] = PostsRow
    inclusion_mode: str = INCLUSION_MODE
    freshness_field: str | None = FRESHNESS_FIELD     # published_at_utc
    primary_key_fields: tuple[str, ...] = PRIMARY_KEYS
    default_chunk_size: int = 5000
    supports_incremental: bool = True

    # ── Source column contract ────────────────────────────────────────────────

    def get_source_columns(self) -> tuple[str, ...]:
        """
        Return the explicit ordered source columns for dim_posts.

        These columns must stay aligned with PostsRow.from_row().
        Adding or removing a column here requires a matching change in
        the schema row dataclass.
        """
        return (
            "post_id",
            "author_user_id",
            "title",
            "description",
            "content",
            "url",
            "image",
            "video",
            "published_at_utc",
            "like_count",
            "view_count",
            "is_active",
            "clap_count",
            "fire_count",
            "football_count",
            "thumbs_down_count",
            "thumbs_up_count",
        )

    # ── Query construction ────────────────────────────────────────────────────

    def build_base_query(self) -> str:
        """
        Return the base SELECT for dim_posts without incremental filtering.

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
        Return stable deterministic ordering for dim_posts.

        published_at_utc first — aligns with watermark advancement and
        clusters output by publication time, matching the most common
        downstream consumption pattern for post content ingestion.

        post_id second — VARCHAR PK; breaks ties within the same publication
        timestamp bucket deterministically.
        """
        return "\nORDER BY published_at_utc, post_id"

    def build_pagination_clause(self, limit: int, offset: int) -> str:
        """
        Return LIMIT/OFFSET pagination clause.
        """
        return "\nLIMIT %(limit)s OFFSET %(offset)s"