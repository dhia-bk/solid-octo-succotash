"""
Extractor for the dim_comments warehouse source.

Purpose:
- Extract comment content from dim_comments, including author, parent
  relationships, content, timestamp, and reaction counts.
- Incremental strategy using created_at_utc as the watermark.
- Return typed CommentsRow instances wrapped in ExtractorBatch.

Source characteristics:
    dim_comments holds one row per comment. Reaction counts (like_count,
    clap_count, fire_count, football_count, thumbs_up_count,
    thumbs_down_count) are updated in-place as engagement accumulates,
    meaning rows can mutate after the original created_at_utc timestamp.
    The same tradeoff as dim_posts applies: incremental by created_at_utc
    captures new comments correctly but misses engagement count updates on
    older comments. Up-to-date engagement aggregates are available via
    fct_content_engagement_daily.

    parent_comment_id enables thread nesting (REPLIES_TO edges). It is NULL
    for top-level comments. The extractor must preserve it exactly so the
    transformer can construct the correct comment thread graph structure.

Design rules:
- comment_id, post_id, and parent_comment_id are all VARCHAR in the DWH;
  preserved as str / str | None. No SQL-level coercion applied.
- parent_comment_id must be preserved faithfully — NULL vs non-NULL carries
  structural meaning for REPLIES_TO edge construction.
- user_id is a string FK to dim_users; preserved as-is.
- post_id is a string FK to dim_posts; preserved as-is.
- No graph logic, canonicalization, or enrichment is applied here.

Source schema:
- Source table  : dim_comments
- Inclusion mode: GRAPH_CORE
- Graph entity  : Comment
- Freshness field: created_at_utc
"""

from __future__ import annotations

from app.contracts.warehouse_rows import WarehouseRow
from app.extractors.base import BaseExtractor
from app.schemas.warehouse.comments import (
    FRESHNESS_FIELD,
    INCLUSION_MODE,
    PRIMARY_KEYS,
    SOURCE_NAME,
    CommentsRow,
)


class CommentsExtractor(BaseExtractor):
    """
    Extractor for dim_comments.

    Incremental strategy:
    - watermark field: created_at_utc
    - ordering: created_at_utc, comment_id

    Thread structure preservation:
    - parent_comment_id is NULL for top-level comments and non-NULL for
      replies. Both cases must be extracted faithfully; the extractor does
      not filter on parent_comment_id or attempt to reconstruct thread
      hierarchy — that belongs to the transformer layer.

    Engagement count limitation:
    - Reaction counts mutate after creation. Incremental runs capture new
      comments only; count updates on existing comments are not re-extracted.
      Use fct_content_engagement_daily for up-to-date engagement aggregates.
    """

    source_name: str = SOURCE_NAME
    schema_row_class: type[WarehouseRow] = CommentsRow
    inclusion_mode: str = INCLUSION_MODE
    freshness_field: str | None = FRESHNESS_FIELD     # created_at_utc
    primary_key_fields: tuple[str, ...] = PRIMARY_KEYS
    default_chunk_size: int = 5000
    supports_incremental: bool = True

    # ── Source column contract ────────────────────────────────────────────────

    def get_source_columns(self) -> tuple[str, ...]:
        """
        Return the explicit ordered source columns for dim_comments.

        These columns must stay aligned with CommentsRow.from_row().
        Adding or removing a column here requires a matching change in
        the schema row dataclass.

        Thread structure note:
            parent_comment_id is NULL for top-level comments and non-NULL
            for replies. Must be preserved as-is; NULL carries structural
            meaning for REPLIES_TO edge construction in the transformer.
        """
        return (
            "comment_id",
            "user_id",
            "post_id",
            "content",
            "created_at_utc",
            "like_count",
            "parent_comment_id",   # NULL = top-level; non-NULL = reply
            "clap_count",
            "fire_count",
            "football_count",
            "thumbs_down_count",
            "thumbs_up_count",
        )

    # ── Query construction ────────────────────────────────────────────────────

    def build_base_query(self) -> str:
        """
        Return the base SELECT for dim_comments without incremental filtering.

        The incremental clause (WHERE created_at_utc > :watermark_value)
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

        return f"\nWHERE {self.freshness_field} > :watermark_value"

    def build_order_by_clause(self) -> str:
        """
        Return stable deterministic ordering for dim_comments.

        created_at_utc first — aligns with watermark advancement and clusters
        output by creation time, matching the natural downstream consumption
        pattern for comment thread ingestion.

        comment_id second — VARCHAR PK; breaks ties within the same creation
        timestamp bucket deterministically.
        """
        return "\nORDER BY created_at_utc, comment_id"

    def build_pagination_clause(self, limit: int, offset: int) -> str:
        """
        Return LIMIT/OFFSET pagination clause.
        """
        return "\nLIMIT %(limit)s OFFSET %(offset)s"