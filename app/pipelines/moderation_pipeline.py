"""
Moderation pipeline — moderation events.

Requires identity_pipeline (User for MODERATED rels).
"""

from __future__ import annotations

from app.core.constants import MODERATION_PIPELINE
from app.pipelines.base import BasePipeline


class ModerationPipeline(BasePipeline):
    """Loads ModerationEvent nodes and MODERATED relationships."""

    pipeline_name = MODERATION_PIPELINE
    sources = (
        "fct_moderation_events",  # ModerationEvent nodes + MODERATED rels
    )
