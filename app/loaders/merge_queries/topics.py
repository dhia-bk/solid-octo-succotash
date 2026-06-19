"""
Merge queries for topics.
Source(s): fct_topics
"""

from __future__ import annotations

from app.loaders.merge_queries.base import (
    build_node_merge_query,
    build_relationship_merge_query,
)


def get_topic_merge_query(source_name: str = "fct_topics") -> str:
    """Return Cypher MERGE query for Topic nodes from source_name."""
    return build_node_merge_query(
        label="Topic",
        merge_key_field="id",
        write_once_fields=[],
        mutable_fields=[
            "topic_label",
            "topic_category",
            "confidence_score",
            "is_trending",
        ],
    )


def get_discussed_merge_query(source_name: str = "fct_topics") -> str:
    """Return Cypher MERGE query for DISCUSSED (Post→Topic) from source_name."""
    return build_relationship_merge_query(
        rel_type="DISCUSSED",
        start_label="Post",
        end_label="Topic",
        start_merge_field="id",
        end_merge_field="id",
        rel_merge_fields=None,
        rel_property_fields=["relevance_score", "discussed_at"],
    )
