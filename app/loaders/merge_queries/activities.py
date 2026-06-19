"""
Merge queries for user activities.
Source(s): fct_user_activities
"""

from __future__ import annotations

from app.loaders.merge_queries.base import build_relationship_merge_query


def get_liked_post_merge_query(source_name: str = "fct_user_activities") -> str:
    """Return Cypher MERGE query for LIKED (User→Post) from source_name."""
    return build_relationship_merge_query(
        rel_type="LIKED",
        start_label="User",
        end_label="Post",
        start_merge_field="id",
        end_merge_field="id",
        rel_merge_fields=["activity_id"],
        rel_property_fields=["activity_at", "activity_weight"],
    )


def get_liked_comment_merge_query(source_name: str = "fct_user_activities") -> str:
    """Return Cypher MERGE query for LIKED (User→Comment) from source_name."""
    return build_relationship_merge_query(
        rel_type="LIKED",
        start_label="User",
        end_label="Comment",
        start_merge_field="id",
        end_merge_field="id",
        rel_merge_fields=["activity_id"],
        rel_property_fields=["activity_at", "activity_weight"],
    )


def get_answered_merge_query(source_name: str = "fct_user_activities") -> str:
    """Return Cypher MERGE query for ANSWERED (User→Poll) from source_name."""
    return build_relationship_merge_query(
        rel_type="ANSWERED",
        start_label="User",
        end_label="Poll",
        start_merge_field="id",
        end_merge_field="id",
        rel_merge_fields=["activity_id"],
        rel_property_fields=["activity_at", "answer_value"],
    )


def get_friended_merge_query(source_name: str = "fct_user_activities") -> str:
    """Return Cypher MERGE query for FRIENDED (User→User) from source_name."""
    return build_relationship_merge_query(
        rel_type="FRIENDED",
        start_label="User",
        end_label="User",
        start_merge_field="id",
        end_merge_field="id",
        rel_merge_fields=["activity_id"],
        rel_property_fields=["activity_at", "activity_weight"],
    )
