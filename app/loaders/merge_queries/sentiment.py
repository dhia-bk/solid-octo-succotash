"""
Merge queries for sentiment analysis.
Source(s): fct_sentiment
"""

from __future__ import annotations

from app.loaders.merge_queries.base import (
    build_node_merge_query,
    build_relationship_merge_query,
)


def get_sentiment_merge_query(source_name: str = "fct_sentiment") -> str:
    """Return Cypher MERGE query for Sentiment nodes from source_name."""
    return build_node_merge_query(
        label="Sentiment",
        merge_key_field="id",
        write_once_fields=[],
        mutable_fields=[
            "source_type",
            "item_id",
            "user_id",
            "sentiment_label",
            "score_positive",
            "score_negative",
            "score_neutral",
            "analysed_at",
        ],
    )


def get_expressed_merge_query(source_name: str = "fct_sentiment") -> str:
    """Return Cypher MERGE query for EXPRESSED (User→Sentiment) from source_name."""
    return build_relationship_merge_query(
        rel_type="EXPRESSED",
        start_label="User",
        end_label="Sentiment",
        start_merge_field="id",
        end_merge_field="id",
        rel_merge_fields=None,
        rel_property_fields=["analysed_at"],
    )
