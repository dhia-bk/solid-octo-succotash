"""
Communication pipeline — notification content, recipients, user preferences.

Content nodes before recipient relationships (FK: NotificationContent node
must exist before RECEIVED_NOTIFICATION rel is written).
Requires identity_pipeline (User for rels and preference enrichment).
"""

from __future__ import annotations

from app.core.constants import COMMUNICATION_PIPELINE
from app.pipelines.base import BasePipeline


class CommunicationPipeline(BasePipeline):
    """
    Loads notification domain: NotificationContent, RECEIVED_NOTIFICATION rels,
    User notification preference enrichment.
    """

    pipeline_name = COMMUNICATION_PIPELINE
    sources = (
        "dim_notification_content",      # NotificationContent nodes
        "jct_notification_recipients",   # RECEIVED_NOTIFICATION rels
        "dim_notification_preferences",  # User enrichment (notification prefs)
    )
