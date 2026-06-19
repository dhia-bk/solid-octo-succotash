"""
Merge queries for team affinity.
Source(s): fct_team_affinity
"""

from __future__ import annotations

from app.loaders.merge_queries.base import build_relationship_merge_query


def get_has_affinity_merge_query(source_name: str = "fct_team_affinity") -> str:
    """Return Cypher MERGE query for HAS_AFFINITY (User→Team) from source_name."""
    return build_relationship_merge_query(
        rel_type="HAS_AFFINITY",
        start_label="User",
        end_label="Team",
        start_merge_field="id",
        end_merge_field="id",
        rel_merge_fields=["affinity_id"],
        rel_property_fields=[
            "affinity_score",
            "affinity_level",
            "calculated_at",
            "activity_weight",
        ],
    )
