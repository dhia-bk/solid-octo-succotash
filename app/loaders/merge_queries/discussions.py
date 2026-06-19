"""
Merge queries for discussions.
Source(s): dim_discussions, dim_prediction_discussions, fct_discussion_events
"""

from __future__ import annotations

from app.loaders.merge_queries.base import (
    build_node_merge_query,
    build_relationship_merge_query,
)


def get_discussion_merge_query(source_name: str = "dim_discussions") -> str:
    """Return Cypher MERGE query for Discussion from source_name."""
    return build_node_merge_query(
        label="Discussion",
        merge_key_field="id",
        write_once_fields=[],
        mutable_fields=[
            "discussion_title",
            "discussion_type",
            "fixture_id",
            "post_count",
            "participant_count",
            "is_active",
        ],
    )


def get_prediction_discussion_merge_query(
    source_name: str = "dim_prediction_discussions",
) -> str:
    """Return Cypher MERGE query for PredictionDiscussion from source_name."""
    return build_node_merge_query(
        label="PredictionDiscussion",
        merge_key_field="id",
        write_once_fields=[],
        mutable_fields=[
            "fixture_id",
            "prediction_count",
            "is_active",
        ],
    )


def get_joined_discussion_merge_query(
    source_name: str = "fct_discussion_events",
) -> str:
    """Return Cypher MERGE query for JOINED_DISCUSSION (User→Discussion) from source_name."""
    return build_relationship_merge_query(
        rel_type="JOINED_DISCUSSION",
        start_label="User",
        end_label="Discussion",
        start_merge_field="id",
        end_merge_field="id",
        rel_merge_fields=["event_type"],
        rel_property_fields=["event_at", "action_type"],
    )


def get_about_merge_query(source_name: str = "dim_prediction_discussions") -> str:
    """Return Cypher MERGE query for ABOUT (PredictionDiscussion→Match) from source_name."""
    return build_relationship_merge_query(
        rel_type="ABOUT",
        start_label="PredictionDiscussion",
        end_label="Match",
        start_merge_field="id",
        end_merge_field="id",
        rel_merge_fields=None,
        rel_property_fields=[],
    )
