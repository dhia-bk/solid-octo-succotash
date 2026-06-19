"""
Merge queries for League nodes.
Source(s): dim_leagues
"""

from __future__ import annotations

from app.loaders.merge_queries.base import build_node_merge_query


def get_league_merge_query(source_name: str = "dim_leagues") -> str:
    """Return Cypher MERGE query for League nodes from source_name."""
    return build_node_merge_query(
        label="League",
        merge_key_field="id",
        write_once_fields=[],
        mutable_fields=["league_name", "league_code", "country", "is_active"],
    )
