"""
Extractor for the dim_ai_articles warehouse source.

Purpose:
- Extract AI-generated article rows from dim_ai_articles, including
  generation and publishing state, match/news linkage, content body,
  metadata JSON, and engagement counts.
- Incremental strategy using updated_at_utc as the watermark.
- Return typed AiArticlesRow instances wrapped in ExtractorBatch.

No declared primary key:
    dim_ai_articles has no declared PK constraint in the DWH. article_id is
    VARCHAR(50) and is treated as the stable de facto key at extraction time.
    The extractor must not attempt to deduplicate rows — that is a transformer
    concern if duplicates are detected. Stable ordering by updated_at_utc,
    article_id ensures deterministic output across runs.

Watermark field — updated_at_utc:
    updated_at_utc is the correct incremental field for this source because
    dim_ai_articles rows mutate through a multi-stage lifecycle:
    - generation (generated_at_utc populated; generation_succeeded set)
    - editorial approval (approved_at_utc, approved_by_user_id populated)
    - publishing (published_at_utc, status transitions to published)
    - engagement accumulation (view_count, like_count, share_count increment)
    updated_at_utc advances on each mutation, ensuring incremental runs
    capture all lifecycle state changes, not just newly created articles.

Nullable approval and publication fields:
    approved_at_utc, approved_by_user_id, published_at_utc, and
    published_news_id are all NULL for articles that have not yet reached
    those lifecycle stages. They must be extracted faithfully as NULL —
    the transformer uses NULL vs non-NULL to determine current lifecycle
    stage and to gate GENERATED_FOR edge creation.

Design rules:
- article_id is VARCHAR(50) with no declared PK constraint; treated as the
  stable de facto key and used as the ordering tiebreaker.
- match_id is an integer FK to dim_fixtures (match dimension); preserved as-is.
- metadata_json is a raw JSON TEXT field; extracted as a string without
  parsing — JSON parsing belongs to the transformer layer.
- content, summary, and title may be large free-text fields; extracted
  faithfully — field-length enforcement is a loader concern.
- No graph logic, canonicalization, or enrichment is applied here.

Source schema:
- Source table  : dim_ai_articles
- Inclusion mode: GRAPH_CORE
- Graph entity  : AIArticle
- Freshness field: updated_at_utc
- Declared PK   : None (article_id treated as stable de facto key)
"""

from __future__ import annotations

from app.contracts.warehouse_rows import WarehouseRow
from app.extractors.base import BaseExtractor
from app.schemas.warehouse.ai_articles import (
    FRESHNESS_FIELD,
    INCLUSION_MODE,
    PRIMARY_KEYS,
    SOURCE_NAME,
    AiArticlesRow,
)


class AiArticlesExtractor(BaseExtractor):
    """
    Extractor for dim_ai_articles.

    Incremental strategy:
    - watermark field: updated_at_utc
    - ordering: updated_at_utc, article_id

    Lifecycle mutation coverage:
    - updated_at_utc advances through all lifecycle stages (generation,
      approval, publishing, engagement). Incremental runs therefore capture
      all state changes, not only newly created articles.

    Nullable lifecycle fields:
    - approved_at_utc, approved_by_user_id, published_at_utc, and
      published_news_id are NULL for articles not yet at those stages.
      All are extracted faithfully; the transformer gates edge creation on
      NULL vs non-NULL lifecycle state.

    No declared PK:
    - article_id is treated as the stable de facto key. The extractor
      preserves all rows as received; deduplication is a transformer concern.
    """

    source_name: str = SOURCE_NAME
    schema_row_class: type[WarehouseRow] = AiArticlesRow
    inclusion_mode: str = INCLUSION_MODE
    freshness_field: str | None = FRESHNESS_FIELD     # updated_at_utc
    primary_key_fields: tuple[str, ...] = PRIMARY_KEYS
    default_chunk_size: int = 2000                    
    supports_incremental: bool = True

    # ── Source column contract ────────────────────────────────────────────────

    def get_source_columns(self) -> tuple[str, ...]:
        """
        Return the explicit ordered source columns for dim_ai_articles.

        These columns must stay aligned with AiArticlesRow.from_row().
        Adding or removing a column here requires a matching change in
        the schema row dataclass.

        Nullable lifecycle fields note:
            approved_at_utc, approved_by_user_id — NULL until editorial
                approval is granted. Preserved as NULL; transformer gates
                approval-dependent graph writes on these values.
            published_at_utc, published_news_id — NULL until the article is
                published. Preserved as NULL; transformer gates publishing-
                dependent edge creation (GENERATED_FOR → Match) on these.

        metadata_json note:
            Raw JSON TEXT field. Extracted as-is without parsing.
            JSON parsing, schema validation, and field extraction belong
            to the transformer layer.

        No-PK note:
            article_id has no declared PK constraint. Treated as the stable
            de facto key; deduplication belongs to the transformer layer.
        """
        return (
            "article_id",
            "status",
            "generation_succeeded",
            "generated_at_utc",
            "approved_at_utc",          # NULL until approved — see lifecycle note
            "approved_by_user_id",      # NULL until approved — see lifecycle note
            "published_news_id",        # NULL until published — see lifecycle note
            "publication_notes",
            "article_type",
            "content_category",
            "match_id",                 # integer FK to dim_fixtures (match dimension)
            "title",
            "summary",
            "content",
            "image_url",
            "created_at_utc",
            "updated_at_utc",           # extractor watermark field
            "published_at_utc",         # NULL until published — see lifecycle note
            "metadata_json",            # raw JSON string — do not parse here
            "view_count",
            "like_count",
            "share_count",
            "job_id",
        )

    # ── Query construction ────────────────────────────────────────────────────

    def build_base_query(self) -> str:
        """
        Return the base SELECT for dim_ai_articles without incremental
        filtering.

        The incremental clause (WHERE updated_at_utc > :watermark_value)
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
        Build the incremental filter using updated_at_utc.

        Uses strict greater-than semantics so watermark advancement remains
        monotonic across runs. updated_at_utc covers all lifecycle mutations
        (generation, approval, publishing, engagement), so incremental runs
        capture complete lifecycle progression without needing separate
        watermarks per lifecycle stage.

        No clause is emitted on first run (watermark is None), triggering a
        full-table bootstrap load.
        """
        if not self.supports_incremental or not self.freshness_field:
            return ""

        if not watermark_value:
            return ""

        return f"\nWHERE {self.freshness_field} > :watermark_value"

    def build_order_by_clause(self) -> str:
        """
        Return stable deterministic ordering for dim_ai_articles.

        updated_at_utc first — aligns with watermark advancement and clusters
        output by most recent lifecycle mutation.

        article_id second — VARCHAR de facto key; breaks ties within the same
        updated_at_utc bucket deterministically. Absence of a declared PK
        constraint does not affect ordering correctness as long as article_id
        values are unique in practice.
        """
        return "\nORDER BY updated_at_utc, article_id"

    def build_pagination_clause(self, limit: int, offset: int) -> str:
        """
        Return LIMIT/OFFSET pagination clause.
        """
        return "\nLIMIT %(limit)s OFFSET %(offset)s"