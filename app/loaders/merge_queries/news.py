"""
Merge queries for news articles.
Source(s): dim_news
"""

from __future__ import annotations

from app.loaders.merge_queries.base import build_node_merge_query


def get_news_merge_query(source_name: str = "dim_news") -> str:
    """Return Cypher MERGE query for News nodes."""
    return build_node_merge_query(
        label="News",
        merge_key_field="id",
        write_once_fields=["published_at"],
        mutable_fields=[
            "title",
            "content",
            "author",
            "url",
            "image",
            "is_active",
        ],
    )
