"""
Merge queries for AI articles.
Source(s): dim_ai_articles
"""

from __future__ import annotations

from app.loaders.merge_queries.base import build_node_merge_query


def get_ai_article_merge_query(source_name: str = "dim_ai_articles") -> str:
    """Return Cypher MERGE query for AIArticle nodes."""
    return build_node_merge_query(
        label="AIArticle",
        merge_key_field="id",
        write_once_fields=["published_at"],
        mutable_fields=[
            "title",
            "summary",
            "topic_label",
            "source_url",
            "language",
            "is_featured",
            "view_count",
        ],
    )
