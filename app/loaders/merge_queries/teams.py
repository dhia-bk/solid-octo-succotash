"""
Merge queries for Team nodes and Team enrichment.
Source(s): dim_teams, dim_teams_enhanced
"""

from __future__ import annotations

from app.loaders.merge_queries.base import (
    build_enrichment_merge_query,
    build_node_merge_query,
)


def get_team_merge_query(source_name: str = "dim_teams") -> str:
    """Return Cypher MERGE query for Team nodes from source_name."""
    return build_node_merge_query(
        label="Team",
        merge_key_field="id",
        write_once_fields=[],
        mutable_fields=["team_name", "team_code", "country", "league_id"],
    )


def get_team_enrichment_merge_query(source_name: str = "dim_teams_enhanced") -> str:
    """Return Cypher MERGE query for Team enrichment from source_name."""
    return build_enrichment_merge_query(
        label="Team",
        merge_key_field="id",
        enrichment_fields=[],
        write_policy_overwrite=[
            "total_fans",
            "fan_rank",
            "fan_engagement_score",
            "fan_growth_rate",
        ],
        write_policy_fill_if_null=["team_logo"],
    )
