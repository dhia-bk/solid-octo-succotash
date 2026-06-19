"""
Merge queries for Badge nodes.
Source(s): dim_badges
"""

from __future__ import annotations

from app.loaders.merge_queries.base import build_node_merge_query


def get_badge_merge_query(source_name: str = "dim_badges") -> str:
    """Return Cypher MERGE query for Badge nodes from source_name."""
    return build_node_merge_query(
        label="Badge",
        merge_key_field="id",
        write_once_fields=[],
        mutable_fields=[
            "badge_name",
            "badge_type",
            "badge_description",
            "badge_image_url",
            "is_active",
        ],
    )
