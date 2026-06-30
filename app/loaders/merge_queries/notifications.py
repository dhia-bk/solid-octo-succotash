"""
Merge queries for notifications.
Source(s): dim_notification_content, jct_notification_recipients
"""

from __future__ import annotations

from app.loaders.merge_queries.base import build_relationship_merge_query


def get_notification_content_merge_query(
    source_name: str = "dim_notification_content",
) -> str:
    """Return Cypher MERGE query for NotificationContent from source_name.

    Uses a raw Cypher string because the node id may need to fall back between
    content_id and notification_id — a strategy the builder API does not expose.
    """
    return """
UNWIND $rows AS row
MERGE (n:NotificationContent {id: row.id})
ON CREATE SET
    n.normalized_message_text = row.normalized_message_text,
    n.sender_user_id          = row.sender_user_id,
    n.first_seen_at           = row.first_seen_at,
    n.last_seen_at            = row.last_seen_at,
    n._created_at             = row._created_at,
    n._source_name            = row._source_name,
    n._run_id                 = row._run_id
ON MATCH SET
    n.normalized_message_text = row.normalized_message_text,
    n.sender_user_id          = row.sender_user_id,
    n.last_seen_at            = row.last_seen_at,
    n._updated_at             = row._updated_at,
    n._source_name            = row._source_name,
    n._run_id                 = row._run_id
""".strip()


def get_received_notification_merge_query(
    source_name: str = "jct_notification_recipients",
) -> str:
    """Return Cypher MERGE query for RECEIVED_NOTIFICATION (User→NotificationContent) from source_name."""
    return build_relationship_merge_query(
        rel_type="RECEIVED_NOTIFICATION",
        start_label="User",
        end_label="NotificationContent",
        start_merge_field="id",
        end_merge_field="id",
        rel_merge_fields=["notification_id"],
        rel_property_fields=["delivered_at", "read_at", "is_read"],
    )
