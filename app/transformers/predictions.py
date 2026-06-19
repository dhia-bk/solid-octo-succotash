"""
app/transformers/predictions.py
================================
Transformer for fct_predictions → PREDICTED relationships.

Highest-volume source in the pipeline. Emits PREDICTED (User → Match)
relationship records only. No new nodes are created.

prediction_era is read directly from the row (pre-computed by the DWH).
TemporalEngine is used as fallback when row.prediction_era is None.

points_awarded is DECIMAL on the row (float | None) — written as float
to match PredictedRel.points_awarded which is int | None. Coercion via
self._int() per universal rules.
"""

from __future__ import annotations

from app.canonicalization.base import BaseCanonicalizer
from app.contracts.graph_records import GraphWriteBatch, RelationshipRecord
from app.contracts.warehouse_rows import ExtractorBatch
from app.core.constants import MATCH, PREDICTED, USER
from app.core.exceptions import CanonicalizationError, TransformationError
from app.core.ids import build_fixture_id, build_user_id
from app.core.logging import log_transformation_finished, log_transformation_started
from app.mappings.registry import MappingRegistry
from app.schemas.warehouse.predictions import INCLUSION_MODE, SOURCE_NAME, PredictionsRow
from app.transformers.base import BaseTransformer
from app.transformers.graph_record_builder import GraphRecordBuilder
from app.transformers.temporal import TemporalEngine, build_temporal_engine
from app.transformers.weighting import WeightingEngine, build_weighting_engine


class PredictionsTransformer(BaseTransformer):
    """
    Transforms fct_predictions rows into PREDICTED relationship records.

    Merge key strategy: direct on prediction_id (declared in merge_keys.py).
    No endpoint canonicalization required — both user_id and fixture_id are
    direct warehouse IDs.
    """

    source_name = SOURCE_NAME        # "fct_predictions"
    inclusion_mode = INCLUSION_MODE  # GRAPH_CORE

    def __init__(
        self,
        run_id: str,
        canonicalizer_registry: dict[str, BaseCanonicalizer] | None = None,
        mapping_registry: MappingRegistry | None = None,
        temporal_engine: TemporalEngine | None = None,
        weighting_engine: WeightingEngine | None = None,
    ) -> None:
        super().__init__(run_id, canonicalizer_registry, mapping_registry)
        self._temporal = temporal_engine or build_temporal_engine()
        self._weighting = weighting_engine or build_weighting_engine()

    def transform(self, batch: ExtractorBatch) -> GraphWriteBatch:
        self._reset_skip_count()
        builder = GraphRecordBuilder(self._run_id, SOURCE_NAME)
        rels: list[RelationshipRecord] = []

        log_transformation_started(
            self._logger,
            table_name=SOURCE_NAME,
            run_id=self._run_id,
        )

        for row in batch.rows:
            row: PredictionsRow
            try:
                rel = self._transform_row(row, builder)
                if rel is not None:
                    rels.append(rel)
            except (TransformationError, CanonicalizationError) as exc:
                self._skip(str(exc), row_id=getattr(row, "unified_prediction_id", None))
                continue

        log_transformation_finished(
            self._logger,
            record_count=len(rels),
            table_name=SOURCE_NAME,
            run_id=self._run_id,
        )

        return builder.batch([], rels, batch_sequence=0)

    # -- Row-level transform --------------------------------------------------

    def _transform_row(
        self,
        row: PredictionsRow,
        builder: GraphRecordBuilder,
    ) -> RelationshipRecord | None:
        if not row.user_id:
            self._skip(
                "user_id is None — skipping PREDICTED rel",
                row_id=row.unified_prediction_id,
            )
            return None

        if not row.fixture_id:
            self._skip(
                "fixture_id is None — skipping PREDICTED rel",
                row_id=row.unified_prediction_id,
            )
            return None

        is_correct_result = self._bool(row.is_correct_result)

        # Trust DWH prediction_era; fall back to engine when None
        era = row.prediction_era or self._temporal.classify_era(row.predicted_at_utc)

        activity_weight = self._weighting.compute_prediction_weight(
            is_correct_result=is_correct_result,
            points_awarded=self._int(row.points_awarded),
            predicted_at=row.predicted_at_utc,
        )

        properties = {
            "prediction_id":     row.unified_prediction_id,
            "predicted_at":      self._ts(row.predicted_at_utc),
            "predicted_outcome": row.predicted_outcome,
            "points_awarded":    self._int(row.points_awarded),
            "is_correct_result": is_correct_result,
            "prediction_era":    era,
            "activity_weight":   activity_weight,
        }

        return builder.rel(
            PREDICTED,
            build_user_id(row.user_id),
            build_fixture_id(row.fixture_id),
            start_label=USER,
            end_label=MATCH,
            properties=properties,
        )