"""
Merge queries for private leagues.
Source(s): dim_private_leagues, dim_influencer_leagues
"""

from __future__ import annotations

from app.loaders.merge_queries.base import (
    build_node_merge_query,
    build_relationship_merge_query,
)


def get_private_league_merge_query(source_name: str = "dim_private_leagues") -> str:
    """Return Cypher MERGE query for PrivateLeague from source_name."""
    return build_node_merge_query(
        label="PrivateLeague",
        merge_key_field="id",
        write_once_fields=["created_at"],
        mutable_fields=[
            "league_name",
            "member_count",
            "max_members",
            "is_public",
            "creator_user_id",
            "season_id",
        ],
    )


def get_promotes_merge_query(source_name: str = "dim_influencer_leagues") -> str:
    """Return Cypher MERGE query for PROMOTES (User→InfluencerLeague) from source_name."""
    return build_relationship_merge_query(
        rel_type="PROMOTES",
        start_label="User",
        end_label="InfluencerLeague",
        start_merge_field="id",
        end_merge_field="id",
        rel_merge_fields=None,
        rel_property_fields=[],
    )
