"""
Merge queries for tags.
Source(s): dim_tags, dim_posts, dim_news, dim_ai_articles
"""

from __future__ import annotations

from app.loaders.merge_queries.base import (
    build_node_merge_query,
    build_relationship_merge_query,
)


def get_tag_merge_query(source_name: str = "dim_tags") -> str:
    """Return Cypher MERGE query for Tag from source_name."""
    return build_node_merge_query(
        label="Tag",
        merge_key_field="id",
        write_once_fields=[],
        mutable_fields=[
            "tag_name",
            "tag_type",
            "is_trending",
            "usage_count",
        ],
    )


def get_post_has_tag_merge_query(source_name: str = "dim_posts") -> str:
    """Return Cypher MERGE query for HAS_TAG (Post→Tag) from source_name."""
    return build_relationship_merge_query(
        rel_type="HAS_TAG",
        start_label="Post",
        end_label="Tag",
        start_merge_field="id",
        end_merge_field="id",
        rel_merge_fields=None,
        rel_property_fields=["tagged_at"],
    )


def get_news_has_tag_merge_query(source_name: str = "dim_news") -> str:
    """Return Cypher MERGE query for HAS_TAG (News→Tag) from source_name."""
    return build_relationship_merge_query(
        rel_type="HAS_TAG",
        start_label="News",
        end_label="Tag",
        start_merge_field="id",
        end_merge_field="id",
        rel_merge_fields=None,
        rel_property_fields=["tagged_at"],
    )


def get_ai_article_has_tag_merge_query(source_name: str = "dim_ai_articles") -> str:
    """Return Cypher MERGE query for HAS_TAG (AIArticle→Tag) from source_name."""
    return build_relationship_merge_query(
        rel_type="HAS_TAG",
        start_label="AIArticle",
        end_label="Tag",
        start_merge_field="id",
        end_merge_field="id",
        rel_merge_fields=None,
        rel_property_fields=["tagged_at"],
    )
