"""
app/transformers/product_analytics.py
=======================================
Non-emitting transformer for three product analytics sources.

All three sources are SERVING_ONLY or FEATURE_SOURCE and do not emit
graph records. This transformer exists solely to satisfy the pipeline
lifecycle contract — logging started/finished events — for sources that
feed dashboards and feature models only.

Sources handled:
    "fct_daily_metrics"             — SERVING_ONLY (operational dashboard)
    "fct_content_engagement_daily"  — SERVING_ONLY (engagement aggregates)
    "fct_retention_cohorts"         — SERVING_ONLY (retention dashboard)
"""

from __future__ import annotations

from app.contracts.graph_records import GraphWriteBatch
from app.contracts.warehouse_rows import ExtractorBatch
from app.core.exceptions import TransformationError
from app.core.logging import log_transformation_finished, log_transformation_started
from app.mappings.source_to_graph import source_emits_graph_records
from app.transformers.base import BaseTransformer
from app.transformers.graph_record_builder import GraphRecordBuilder

_DAILY_METRICS_SOURCE = "fct_daily_metrics"
_ENGAGEMENT_SOURCE = "fct_content_engagement_daily"
_RETENTION_SOURCE = "fct_retention_cohorts"

_HANDLED_SOURCES = frozenset({
    _DAILY_METRICS_SOURCE,
    _ENGAGEMENT_SOURCE,
    _RETENTION_SOURCE,
})

SOURCE_NAME = _DAILY_METRICS_SOURCE
INCLUSION_MODE = "serving_only"


class ProductAnalyticsTransformer(BaseTransformer):
    """
    Non-emitting transformer for product analytics sources.

    All three sources return an empty GraphWriteBatch immediately after
    logging lifecycle events.
    """

    source_name = SOURCE_NAME
    inclusion_mode = INCLUSION_MODE

    def transform(self, batch: ExtractorBatch) -> GraphWriteBatch:
        if batch.source_name not in _HANDLED_SOURCES:
            raise TransformationError(
                f"ProductAnalyticsTransformer received unexpected source '{batch.source_name}'",
                source=batch.source_name,
            )

        self._reset_skip_count()
        builder = GraphRecordBuilder(self._run_id, batch.source_name)

        log_transformation_started(
            self._logger,
            table_name=batch.source_name,
            run_id=self._run_id,
        )

        if not source_emits_graph_records(batch.source_name):
            log_transformation_finished(
                self._logger,
                record_count=0,
                table_name=batch.source_name,
                run_id=self._run_id,
            )
            return builder.batch([], [], 0)

        log_transformation_finished(
            self._logger,
            record_count=0,
            table_name=batch.source_name,
            run_id=self._run_id,
        )
        return builder.batch([], [], 0)