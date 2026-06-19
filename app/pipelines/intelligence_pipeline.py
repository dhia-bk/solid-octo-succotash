"""
Intelligence pipeline — ML-derived topics, sentiment, team affinity.

Requires identity_pipeline (User) and sports_pipeline (Team for HAS_AFFINITY).
"""

from __future__ import annotations

from app.core.constants import INTELLIGENCE_PIPELINE
from app.pipelines.base import BasePipeline


class IntelligencePipeline(BasePipeline):
    """
    Loads ML intelligence nodes and relationships: Topic, Sentiment, HAS_AFFINITY.
    """

    pipeline_name = INTELLIGENCE_PIPELINE
    sources = (
        "fct_topics",       # Topic nodes + DISCUSSED rels
        "fct_sentiment",    # Sentiment nodes + EXPRESSED rels
        "fct_team_affinity", # HAS_AFFINITY rels (User → Team)
    )
