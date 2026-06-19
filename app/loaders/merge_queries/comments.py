"""
Merge queries for comments.
Source(s): dim_comments
"""

from __future__ import annotations

from app.loaders.merge_queries.base import build_node_merge_query


def get_comment_merge_query(source_name: str = "dim_comments") -> str:
    """Return Cypher MERGE query for Comment from source_name."""
    return build_node_merge_query(
        label="Comment",
        merge_key_field="id",
        write_once_fields=["created_at"],
        mutable_fields=[
            "content_preview",
            "parent_comment_id",
            "post_id",
            "is_moderated",
            "like_count",
        ],
    )
