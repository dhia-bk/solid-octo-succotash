"""
Analytics feature pipeline — non-emitting analytics and serving-only feature sources.

All five sources are FEATURE_SOURCE or SERVING_ONLY. This pipeline runs
lifecycle log events and coverage checks but produces no graph records.
"""

from __future__ import annotations

from app.core.constants import ANALYTICS_FEATURE_PIPELINE
from app.pipelines.base import BasePipeline


class AnalyticsFeaturePipeline(BasePipeline):
    """
    Processes non-emitting analytics feature sources.

    All sources return non_emitting SourceRunResult — lifecycle events only.
    """

    pipeline_name = ANALYTICS_FEATURE_PIPELINE
    sources = (
        "fct_team_daily_growth",         # non-emitting
        "fct_heatmap_events",            # non-emitting
        "fct_daily_metrics",             # non-emitting
        "fct_content_engagement_daily",  # non-emitting
        "fct_retention_cohorts",         # non-emitting
    )
