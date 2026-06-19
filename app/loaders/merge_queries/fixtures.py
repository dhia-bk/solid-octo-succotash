"""
Merge queries for Match nodes and fixture relationships.
Source(s): dim_fixtures, dim_teams
"""

from __future__ import annotations

from app.loaders.merge_queries.base import (
    build_node_merge_query,
    build_relationship_merge_query,
)


def get_match_merge_query(source_name: str = "dim_fixtures") -> str:
    """Return Cypher MERGE query for Match nodes from source_name."""
    return build_node_merge_query(
        label="Match",
        merge_key_field="id",
        write_once_fields=[],
        mutable_fields=[
            "kickoff_at",
            "status",
            "home_team_id",
            "away_team_id",
            "league_id",
            "home_score",
            "away_score",
            "is_finished",
        ],
    )


def get_home_team_merge_query(source_name: str = "dim_fixtures") -> str:
    """Return Cypher MERGE query for HOME_TEAM relationships from source_name."""
    return build_relationship_merge_query(
        rel_type="HOME_TEAM",
        start_label="Match",
        end_label="Team",
        start_merge_field="id",
        end_merge_field="id",
        rel_merge_fields=None,
        rel_property_fields=[],
    )


def get_away_team_merge_query(source_name: str = "dim_fixtures") -> str:
    """Return Cypher MERGE query for AWAY_TEAM relationships from source_name."""
    return build_relationship_merge_query(
        rel_type="AWAY_TEAM",
        start_label="Match",
        end_label="Team",
        start_merge_field="id",
        end_merge_field="id",
        rel_merge_fields=None,
        rel_property_fields=[],
    )


def get_in_league_merge_query(source_name: str = "dim_fixtures") -> str:
    """Return Cypher MERGE query for IN_LEAGUE relationships from source_name."""
    return build_relationship_merge_query(
        rel_type="IN_LEAGUE",
        start_label="Match",
        end_label="League",
        start_merge_field="id",
        end_merge_field="id",
        rel_merge_fields=None,
        rel_property_fields=[],
    )


def get_played_in_merge_query(source_name: str = "dim_fixtures") -> str:
    """Return Cypher MERGE query for PLAYED_IN relationships from source_name."""
    return build_relationship_merge_query(
        rel_type="PLAYED_IN",
        start_label="Team",
        end_label="League",
        start_merge_field="id",
        end_merge_field="id",
        rel_merge_fields=None,
        rel_property_fields=[],
    )


def get_plays_in_merge_query(source_name: str = "dim_teams") -> str:
    """Return Cypher MERGE query for PLAYS_IN relationships from source_name."""
    return build_relationship_merge_query(
        rel_type="PLAYS_IN",
        start_label="Team",
        end_label="League",
        start_merge_field="id",
        end_merge_field="id",
        rel_merge_fields=None,
        rel_property_fields=[],
    )
