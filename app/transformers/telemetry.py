"""
app/transformers/telemetry.py
==============================
Non-emitting transformer for fct_heatmap_events.

fct_heatmap_events is a FEATURE_SOURCE — high-volume telemetry events
that feed the analytics feature pipeline only. Does not emit graph records.
"""

from __future__ import annotations

from app.contracts.graph_records import GraphWriteBatch
from app.contracts.warehouse_rows import ExtractorBatch
from app.core.logging import log_transformation_finished, log_transformation_started
from app.mappings.source_to_graph import source_emits_graph_records
from app.transformers.base import BaseTransformer
from app.transformers.graph_record_builder import GraphRecordBuilder

SOURCE_NAME = "fct_heatmap_events"
INCLUSION_MODE = "feature_source"


class TelemetryTransformer(BaseTransformer):

    source_name = SOURCE_NAME
    inclusion_mode = INCLUSION_MODE

    def transform(self, batch: ExtractorBatch) -> GraphWriteBatch:
        self._reset_skip_count()
        builder = GraphRecordBuilder(self._run_id, SOURCE_NAME)

        log_transformation_started(self._logger, table_name=SOURCE_NAME, run_id=self._run_id)

        if not source_emits_graph_records(SOURCE_NAME):
            log_transformation_finished(self._logger, record_count=0, table_name=SOURCE_NAME, run_id=self._run_id)
            return builder.batch([], [], 0)

        log_transformation_finished(self._logger, record_count=0, table_name=SOURCE_NAME, run_id=self._run_id)
        return builder.batch([], [], 0)