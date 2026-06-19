"""
Merge queries for prediction duels.
Source(s): fct_prediction_duels
"""

from __future__ import annotations

from app.loaders.merge_queries.base import (
    build_node_merge_query,
    build_relationship_merge_query,
)


def get_duel_merge_query(source_name: str = "fct_prediction_duels") -> str:
    """Return Cypher MERGE query for Duel nodes from source_name."""
    return build_node_merge_query(
        label="Duel",
        merge_key_field="id",
        write_once_fields=[],
        mutable_fields=[
            "challenger_id",
            "opponent_id",
            "fixture_id",
            "duel_status",
            "challenger_points",
            "opponent_points",
            "winner_id",
            "duel_at",
            "settled_at",
        ],
    )


def get_challenged_merge_query(source_name: str = "fct_prediction_duels") -> str:
    """Return Cypher MERGE query for CHALLENGED (User→Duel) from source_name."""
    return build_relationship_merge_query(
        rel_type="CHALLENGED",
        start_label="User",
        end_label="Duel",
        start_merge_field="id",
        end_merge_field="id",
        rel_merge_fields=None,
        rel_property_fields=["duel_at", "role"],
    )
