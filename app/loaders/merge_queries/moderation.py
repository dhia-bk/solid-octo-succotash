"""
Merge queries for moderation events.
Source(s): fct_moderation_events
"""

from __future__ import annotations

from app.loaders.merge_queries.base import (
    build_node_merge_query,
    build_relationship_merge_query,
)


def get_moderation_event_merge_query(
    source_name: str = "fct_moderation_events",
) -> str:
    """Return Cypher MERGE query for ModerationEvent from source_name."""
    return build_node_merge_query(
        label="ModerationEvent",
        merge_key_field="id",
        write_once_fields=[],
        mutable_fields=[
            "event_type",
            "target_type",
            "target_id",
            "moderator_id",
            "event_at",
            "reason",
            "outcome",
        ],
    )


def get_moderated_merge_query(source_name: str = "fct_moderation_events") -> str:
    """Return Cypher MERGE query for MODERATED (User→ModerationEvent) from source_name."""
    return build_relationship_merge_query(
        rel_type="MODERATED",
        start_label="User",
        end_label="ModerationEvent",
        start_merge_field="id",
        end_merge_field="id",
        rel_merge_fields=None,
        rel_property_fields=["moderated_at", "action_type"],
    )
