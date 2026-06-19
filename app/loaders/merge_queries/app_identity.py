"""
Merge queries for identity and social graph relationships.
Source(s): dim_users
"""

from __future__ import annotations

from app.loaders.merge_queries.base import build_relationship_merge_query


def get_equipped_merge_query(source_name: str = "dim_users") -> str:
    """Return Cypher MERGE query for EQUIPPED relationships from source_name."""
    return build_relationship_merge_query(
        rel_type="EQUIPPED",
        start_label="User",
        end_label="Avatar",
        start_merge_field="id",
        end_merge_field="id",
        rel_merge_fields=None,
        rel_property_fields=["equipped_at"],
    )


def get_favors_merge_query(source_name: str = "dim_users") -> str:
    """Return Cypher MERGE query for FAVORS relationships from source_name."""
    return build_relationship_merge_query(
        rel_type="FAVORS",
        start_label="User",
        end_label="Team",
        start_merge_field="id",
        end_merge_field="id",
        rel_merge_fields=None,
        rel_property_fields=[],
    )
