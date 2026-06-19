"""
Merge queries for achievements and badges.
Source(s): fct_awards_and_achievements
"""

from __future__ import annotations

from app.loaders.merge_queries.base import (
    build_node_merge_query,
    build_relationship_merge_query,
)


def get_achievement_merge_query(
    source_name: str = "fct_awards_and_achievements",
) -> str:
    """Return Cypher MERGE query for Achievement nodes."""
    return build_node_merge_query(
        label="Achievement",
        merge_key_field="id",
        write_once_fields=[],
        mutable_fields=[
            "achievement_name",
            "achievement_type",
            "description",
            "badge_id",
            "points_value",
            "is_active",
        ],
    )


def get_achieved_merge_query(
    source_name: str = "fct_awards_and_achievements",
) -> str:
    """Return Cypher MERGE query for ACHIEVED relationships (User→Achievement)."""
    return build_relationship_merge_query(
        rel_type="ACHIEVED",
        start_label="User",
        end_label="Achievement",
        start_merge_field="id",
        end_merge_field="id",
        rel_merge_fields=None,
        rel_property_fields=["earned_at", "points_awarded"],
    )


def get_awarded_merge_query(
    source_name: str = "fct_awards_and_achievements",
) -> str:
    """Return Cypher MERGE query for AWARDED relationships (User→Badge)."""
    return build_relationship_merge_query(
        rel_type="AWARDED",
        start_label="User",
        end_label="Badge",
        start_merge_field="id",
        end_merge_field="id",
        rel_merge_fields=None,
        rel_property_fields=["earned_at"],
    )
