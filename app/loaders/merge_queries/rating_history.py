"""
Merge queries for user rating history.
Source(s): fct_user_rating_history
"""

from __future__ import annotations

from app.loaders.merge_queries.base import (
    build_node_merge_query,
    build_relationship_merge_query,
)


def get_rating_snapshot_merge_query(source_name: str = "fct_user_rating_history") -> str:
    """Return Cypher MERGE query for RatingSnapshot nodes from source_name."""
    return build_node_merge_query(
        label="RatingSnapshot",
        merge_key_field="id",
        write_once_fields=[],
        mutable_fields=[
            "user_id",
            "rating_value",
            "rating_change",
            "event_type",
            "event_at",
            "duel_id",
        ],
    )


def get_has_rating_merge_query(source_name: str = "fct_user_rating_history") -> str:
    """Return Cypher MERGE query for HAS_RATING (User→RatingSnapshot) from source_name."""
    return build_relationship_merge_query(
        rel_type="HAS_RATING",
        start_label="User",
        end_label="RatingSnapshot",
        start_merge_field="id",
        end_merge_field="id",
        rel_merge_fields=None,
        rel_property_fields=["event_at"],
    )
