"""
Merge queries for Avatar nodes.
Source(s): dim_avatars
"""

from __future__ import annotations

from app.loaders.merge_queries.base import build_node_merge_query


def get_avatar_merge_query(source_name: str = "dim_avatars") -> str:
    """Return Cypher MERGE query for Avatar nodes from source_name."""
    return build_node_merge_query(
        label="Avatar",
        merge_key_field="id",
        write_once_fields=[],
        mutable_fields=[
            "avatar_name",
            "avatar_category",
            "avatar_rarity",
            "is_premium",
            "unlock_cost",
        ],
    )
