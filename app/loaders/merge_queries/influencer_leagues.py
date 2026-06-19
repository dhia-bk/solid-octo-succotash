"""
Merge queries for InfluencerLeague nodes.
Source(s): dim_influencer_leagues
"""

from __future__ import annotations

from app.loaders.merge_queries.base import build_node_merge_query


def get_influencer_league_merge_query(source_name: str = "dim_influencer_leagues") -> str:
    """Return Cypher MERGE query for InfluencerLeague nodes from source_name."""
    return build_node_merge_query(
        label="InfluencerLeague",
        merge_key_field="id",
        write_once_fields=[],
        mutable_fields=[
            "league_name",
            "influencer_user_id",
            "is_active",
            "created_at",
        ],
    )
