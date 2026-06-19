"""
app/transformers/team_affinity.py
==================================
Transformer for fct_team_affinity → HAS_AFFINITY relationships.

Emits HAS_AFFINITY (User → Team) relationship records only.
No new nodes are created.

Endpoint resolution:
    Start: direct user_id (no canonicalization)
    End:   TeamCanonicalizer.resolve_team_id — required=True
           Rows where team_id cannot be canonicalized are skipped.
"""

from __future__ import annotations

from app.canonicalization.teams import TeamCanonicalizer  
from app.contracts.graph_records import GraphWriteBatch, RelationshipRecord
from app.contracts.warehouse_rows import ExtractorBatch
from app.core.constants import HAS_AFFINITY, TEAM, USER
from app.core.exceptions import CanonicalizationError, TransformationError
from app.core.ids import build_user_id
from app.core.logging import log_transformation_finished, log_transformation_started
from app.schemas.warehouse.team_affinity import INCLUSION_MODE, SOURCE_NAME, TeamAffinityRow
from app.transformers.base import BaseTransformer
from app.transformers.graph_record_builder import GraphRecordBuilder


class TeamAffinityTransformer(BaseTransformer):
    """
    Transforms fct_team_affinity rows into HAS_AFFINITY relationship records.

    Merge key strategy: direct on affinity_id (declared in merge_keys.py).
    Team endpoint resolution uses self._resolve_endpoint() which dispatches
    through HAS_AFFINITY_END spec → TeamCanonicalizer.resolve_team_id.
    TeamCanonicalizer must be injected via canonicalizer_registry.
    """

    source_name = SOURCE_NAME        # "fct_team_affinity"
    inclusion_mode = INCLUSION_MODE  # GRAPH_CORE

    def transform(self, batch: ExtractorBatch) -> GraphWriteBatch:
        self._reset_skip_count()
        builder = GraphRecordBuilder(self._run_id, SOURCE_NAME)
        rels: list[RelationshipRecord] = []

        # Verify injected canonicalizer is TeamCanonicalizer
        canon = self._canonicalizers.get("teams")
        if not isinstance(canon, TeamCanonicalizer):
            raise TransformationError(
                "TeamAffinityTransformer requires a TeamCanonicalizer injected "
                "under the 'teams' domain key",
                source=SOURCE_NAME,
            )

        log_transformation_started(
            self._logger,
            table_name=SOURCE_NAME,
            run_id=self._run_id,
        )

        for row in batch.rows:
            row: TeamAffinityRow
            try:
                rel = self._transform_row(row, builder)
                if rel is not None:
                    rels.append(rel)
            except (TransformationError, CanonicalizationError) as exc:
                self._skip(str(exc), row_id=getattr(row, "affinity_id", None))
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
        row: TeamAffinityRow,
        builder: GraphRecordBuilder,
    ) -> RelationshipRecord | None:
        if not row.user_id:
            self._skip(
                "user_id is None — skipping HAS_AFFINITY rel",
                row_id=row.affinity_id,
            )
            return None

        if not row.team_id:
            self._skip(
                "team_id is None — skipping HAS_AFFINITY rel",
                row_id=row.affinity_id,
            )
            return None

        # Team endpoint — dispatches through HAS_AFFINITY_END spec
        # → TeamCanonicalizer.resolve_team_id (required=True)
        try:
            team_node_id = self._resolve_endpoint(HAS_AFFINITY, "end", row.team_id)
        except TransformationError as exc:
            self._skip(str(exc), row_id=row.affinity_id, team_id=row.team_id)
            return None

        if team_node_id is None:
            return None

        user_node_id = build_user_id(row.user_id)

        properties = {
            "affinity_type":           row.affinity_type,
            "total_predictions":       row.total_predictions,
            "prediction_accuracy_rate": row.prediction_accuracy_rate,
            "is_favorite_team":        self._bool(row.is_favorite_team),
            "is_active_fan":           self._bool(row.is_active_fan),
            "calculated_at":           self._ts(row.calculated_at_utc),
        }

        return builder.rel(
            HAS_AFFINITY,
            user_node_id,
            team_node_id,
            start_label=USER,
            end_label=TEAM,
            properties=properties,
        )