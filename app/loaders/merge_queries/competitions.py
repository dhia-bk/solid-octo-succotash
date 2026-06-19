"""
Merge queries for competitions (Super6 rounds and LMS competitions).
Source(s): dim_super6_rounds, dim_super6_round_fixtures, fct_super6_participants, dim_lms_competitions
"""

from __future__ import annotations

from app.loaders.merge_queries.base import (
    build_node_merge_query,
    build_relationship_merge_query,
)


def get_super6_round_merge_query(source_name: str = "dim_super6_rounds") -> str:
    """Return Cypher MERGE query for Super6Round nodes from source_name."""
    return build_node_merge_query(
        label="Super6Round",
        merge_key_field="id",
        write_once_fields=[],
        mutable_fields=[
            "round_name",
            "start_date",
            "end_date",
            "prize_pool",
            "is_active",
        ],
    )


def get_lms_competition_merge_query(source_name: str = "dim_lms_competitions") -> str:
    """Return Cypher MERGE query for LMSCompetition nodes from source_name."""
    return build_node_merge_query(
        label="LMSCompetition",
        merge_key_field="id",
        write_once_fields=[],
        mutable_fields=[
            "competition_name",
            "competition_type",
            "start_date",
            "end_date",
            "is_active",
        ],
    )


def get_participated_in_super6_merge_query(source_name: str = "fct_super6_participants") -> str:
    """Return Cypher MERGE query for PARTICIPATED_IN (User→Super6Round) from source_name."""
    return build_relationship_merge_query(
        rel_type="PARTICIPATED_IN",
        start_label="User",
        end_label="Super6Round",
        start_merge_field="id",
        end_merge_field="id",
        rel_merge_fields=["super6_participant_id"],
        rel_property_fields=["score", "rank", "participated_at"],
    )


def get_participated_in_lms_merge_query(source_name: str = "dim_lms_competitions") -> str:
    """Return Cypher MERGE query for PARTICIPATED_IN (User→LMSCompetition) from source_name."""
    return build_relationship_merge_query(
        rel_type="PARTICIPATED_IN",
        start_label="User",
        end_label="LMSCompetition",
        start_merge_field="id",
        end_merge_field="id",
        rel_merge_fields=None,
        rel_property_fields=["joined_at", "score", "rank"],
    )


def get_has_fixture_merge_query(source_name: str = "dim_super6_round_fixtures") -> str:
    """Return Cypher MERGE query for HAS_FIXTURE (Super6Round→Match) from source_name."""
    return build_relationship_merge_query(
        rel_type="HAS_FIXTURE",
        start_label="Super6Round",
        end_label="Match",
        start_merge_field="id",
        end_merge_field="id",
        rel_merge_fields=None,
        rel_property_fields=["fixture_position"],
    )
