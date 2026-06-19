"""
Warehouse schema for dim_ai_articles.

Source table: dim_ai_articles
Domain: ai_communication
Inclusion mode: GRAPH_CORE — direct graph node creation
Graph entity: AIArticle
Freshness field: updated_at_utc

AI-generated article dimension. No declared PK constraint in the DWH;
article_id treated as the stable key. Feeds AIArticle nodes and
GENERATED_FOR relationship (AIArticle → Match) and HAS_TAG (AIArticle → Tag).

DWH type notes:
    article_id          — VARCHAR(50) in DWH; no PK constraint; str.
    generation_succeeded — TINYINT 0/1.
    metadata_json       — TEXT; raw JSON string — do not parse at schema layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.core.constants import AI_ARTICLE, GRAPH_CORE
from app.core.ids import normalize_nullable_string_id, normalize_string_id
from app.core.time import warehouse_value_to_utc_datetime

# ── Module-level constants ────────────────────────────────────────────────────

SOURCE_NAME: str = "dim_ai_articles"
INCLUSION_MODE: str = GRAPH_CORE
PRIMARY_KEYS: tuple[str, ...] = ("article_id",)
FRESHNESS_FIELD: str | None = "updated_at_utc"
GRAPH_ENTITY_MAPPINGS: tuple[str, ...] = (AI_ARTICLE,)


# ── Row shape ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class AiArticlesRow:
    """
    Typed row shape for dim_ai_articles.

    TINYINT fields (0/1 integers, not booleans in the DWH):
        generation_succeeded

    article_id is VARCHAR(50) with no PK constraint in the DWH; treated as
    the stable de facto key.

    metadata_json is a raw JSON TEXT field. Parsing is the transformer's
    responsibility — do not parse at this layer.
    """

    article_id: str
    status: str | None
    generation_succeeded: int | None
    generated_at_utc: datetime | None
    approved_at_utc: datetime | None
    approved_by_user_id: str | None
    published_news_id: int | None
    publication_notes: str | None
    article_type: str | None
    content_category: str | None
    match_id: int | None
    title: str | None
    summary: str | None
    content: str | None
    image_url: str | None
    created_at_utc: datetime | None
    updated_at_utc: datetime | None
    published_at_utc: datetime | None
    metadata_json: str | None
    view_count: int | None
    like_count: int | None
    share_count: int | None
    job_id: str | None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> AiArticlesRow:
        """Normalize a raw warehouse row into a typed AiArticlesRow."""
        return cls(
            article_id=normalize_string_id(row["article_id"], field_name="article_id"),
            status=row.get("status"),
            generation_succeeded=int(row["generation_succeeded"]) if row.get("generation_succeeded") is not None else None,
            generated_at_utc=warehouse_value_to_utc_datetime(row.get("generated_at_utc")),
            approved_at_utc=warehouse_value_to_utc_datetime(row.get("approved_at_utc")),
            approved_by_user_id=normalize_nullable_string_id(row.get("approved_by_user_id"), field_name="approved_by_user_id"),
            published_news_id=int(row["published_news_id"]) if row.get("published_news_id") is not None else None,
            publication_notes=row.get("publication_notes"),
            article_type=row.get("article_type"),
            content_category=row.get("content_category"),
            match_id=int(row["match_id"]) if row.get("match_id") is not None else None,
            title=row.get("title"),
            summary=row.get("summary"),
            content=row.get("content"),
            image_url=row.get("image_url"),
            created_at_utc=warehouse_value_to_utc_datetime(row.get("created_at_utc")),
            updated_at_utc=warehouse_value_to_utc_datetime(row.get("updated_at_utc")),
            published_at_utc=warehouse_value_to_utc_datetime(row.get("published_at_utc")),
            metadata_json=row.get("metadata_json"),
            view_count=int(row["view_count"]) if row.get("view_count") is not None else None,
            like_count=int(row["like_count"]) if row.get("like_count") is not None else None,
            share_count=int(row["share_count"]) if row.get("share_count") is not None else None,
            job_id=row.get("job_id"),
        )
