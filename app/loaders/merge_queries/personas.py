"""
Merge queries for persona states.
Source(s): fct_user_behavior
"""

from __future__ import annotations

from app.loaders.merge_queries.base import (
    build_node_merge_query,
    build_relationship_merge_query,
)


def get_persona_state_merge_query(source_name: str = "fct_user_behavior") -> str:
    """Return Cypher MERGE query for PersonaState nodes from source_name."""
    return build_node_merge_query(
        label="PersonaState",
        merge_key_field="id",
        write_once_fields=[],
        mutable_fields=[
            "user_id",
            "pcm_stage",
            "behaviour_label",
            "birfing_coefficient",
            "frustration_bias",
            "calculated_at",
            "weighting_version",
        ],
    )


def get_exhibits_merge_query(source_name: str = "fct_user_behavior") -> str:
    """Return Cypher MERGE query for EXHIBITS (User→PersonaState) from source_name."""
    return build_relationship_merge_query(
        rel_type="EXHIBITS",
        start_label="User",
        end_label="PersonaState",
        start_merge_field="id",
        end_merge_field="id",
        rel_merge_fields=None,
        rel_property_fields=["calculated_at"],
    )


def get_has_state_merge_query(source_name: str = "fct_user_behavior") -> str:
    """Return Cypher MERGE query for HAS_STATE (User→PersonaState) from source_name."""
    return build_relationship_merge_query(
        rel_type="HAS_STATE",
        start_label="User",
        end_label="PersonaState",
        start_merge_field="id",
        end_merge_field="id",
        rel_merge_fields=None,
        rel_property_fields=["calculated_at"],
    )


def get_current_state_merge_query(source_name: str = "fct_user_behavior") -> str:
    """Return Cypher MERGE query for CURRENT_STATE (User→PersonaState) from source_name."""
    return build_relationship_merge_query(
        rel_type="CURRENT_STATE",
        start_label="User",
        end_label="PersonaState",
        start_merge_field="id",
        end_merge_field="id",
        rel_merge_fields=None,
        rel_property_fields=["calculated_at"],
    )
