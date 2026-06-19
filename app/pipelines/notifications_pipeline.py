"""
Notifications pipeline — non-emitting notification aggregate sources.

Both sources are FEATURE_SOURCE / SERVING_ONLY. The pipeline runs lifecycle
log events and coverage checks but produces no graph records.
"""

from __future__ import annotations

from app.core.constants import NOTIFICATIONS_PIPELINE
from app.pipelines.base import BasePipeline


class NotificationsPipeline(BasePipeline):
    """
    Processes non-emitting notification feature sources.

    All sources return non_emitting SourceRunResult — lifecycle events only.
    """

    pipeline_name = NOTIFICATIONS_PIPELINE
    sources = (
        "fct_user_notification_stats",    # non-emitting — lifecycle log only
        "fct_notification_content_daily", # non-emitting — lifecycle log only
    )
