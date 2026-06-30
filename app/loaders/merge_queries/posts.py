"""
Merge queries for posts.
Source(s): dim_posts, dim_comments
"""

from __future__ import annotations

from app.loaders.merge_queries.base import (
    build_node_merge_query,
    build_relationship_merge_query,
)


def get_post_merge_query(source_name: str = "dim_posts") -> str:
    """Return Cypher MERGE query for Post from source_name."""
    return build_node_merge_query(
        label="Post",
        merge_key_field="id",
        write_once_fields=["published_at"],
        mutable_fields=[
            "title",
            "description",
            "content",
            "post_type",
            "is_featured",
            "like_count",
            "comment_count",
            "discussion_id",
        ],
    )


def get_posted_merge_query(source_name: str = "dim_posts") -> str:
    """Return Cypher MERGE query for POSTED (User→Post) from source_name."""
    return build_relationship_merge_query(
        rel_type="POSTED",
        start_label="User",
        end_label="Post",
        start_merge_field="id",
        end_merge_field="id",
        rel_merge_fields=None,
        rel_property_fields=[],
    )


def get_commented_merge_query(source_name: str = "dim_comments") -> str:
    """Return Cypher MERGE query for COMMENTED (User→Comment) from source_name."""
    return build_relationship_merge_query(
        rel_type="COMMENTED",
        start_label="User",
        end_label="Comment",
        start_merge_field="id",
        end_merge_field="id",
        rel_merge_fields=None,
        rel_property_fields=[],
    )


def get_replies_to_merge_query(source_name: str = "dim_comments") -> str:
    """Return Cypher MERGE query for REPLIES_TO (Comment→Comment) from source_name."""
    return build_relationship_merge_query(
        rel_type="REPLIES_TO",
        start_label="Comment",
        end_label="Comment",
        start_merge_field="id",
        end_merge_field="id",
        rel_merge_fields=None,
        rel_property_fields=[],
    )
