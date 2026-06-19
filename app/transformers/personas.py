"""
app/transformers/personas.py
=============================
Transformer for fct_user_behavior → PersonaState nodes + CURRENT_STATE
relationships.

Emits:
    - PersonaState node (one per row — each row is a dated snapshot)
    - CURRENT_STATE rel (User → PersonaState) — only for the latest
                        snapshot per user_id within the batch

History builds naturally: each incremental run creates new PersonaState
nodes for users whose state has changed. CURRENT_STATE moves to the new
node; old nodes remain in the graph as the historical chain.

CURRENT_STATE selection:
    Per user_id, the row with the maximum last_calculated_at receives
    CURRENT_STATE. Tiebreak: lower source row id wins.

Property ownership:
    All PersonaState properties are owned by fct_user_behavior
    (APPEND_HISTORY policy) — declared in property_ownership.py.
    may_source_write_property is called per property before inclusion.
"""

from __future__ import annotations

from datetime import datetime

from app.contracts.graph_records import GraphWriteBatch, NodeRecord, RelationshipRecord
from app.contracts.warehouse_rows import ExtractorBatch
from app.core.constants import CURRENT_STATE, PERSONA_STATE, USER
from app.core.exceptions import CanonicalizationError, TransformationError
from app.core.ids import build_persona_state_snapshot_key, build_user_id
from app.core.logging import log_transformation_finished, log_transformation_started
from app.mappings.property_ownership import may_source_write_property
from app.schemas.warehouse.user_behavior import INCLUSION_MODE, SOURCE_NAME, UserBehaviorRow
from app.transformers.base import BaseTransformer
from app.transformers.graph_record_builder import GraphRecordBuilder


class PersonasTransformer(BaseTransformer):
    """
    Transforms fct_user_behavior rows into PersonaState nodes and
    persona relationship records.

    Merge key strategy: direct on user_id (each snapshot is keyed by the
    composite build_persona_state_snapshot_key).
    Node id: build_persona_state_snapshot_key(user_id, behaviour_label,
                                               last_calculated_at)
    """

    source_name = SOURCE_NAME        # "fct_user_behavior"
    inclusion_mode = INCLUSION_MODE  # GRAPH_ENRICHMENT

    def transform(self, batch: ExtractorBatch) -> GraphWriteBatch:
        self._reset_skip_count()
        builder = GraphRecordBuilder(self._run_id, SOURCE_NAME)
        nodes: list[NodeRecord] = []
        rels: list[RelationshipRecord] = []

        log_transformation_started(
            self._logger,
            table_name=SOURCE_NAME,
            run_id=self._run_id,
        )

        # Pre-pass: determine the latest snapshot per user_id for CURRENT_STATE
        latest_per_user = self._find_latest_per_user(batch.rows)

        for row in batch.rows:
            row: UserBehaviorRow
            try:
                if not row.user_id:
                    self._skip("user_id is None — skipping PersonaState row", row_id=row.id)
                    continue

                node, row_rels = self._transform_row(
                    row,
                    builder,
                    is_current=latest_per_user.get(row.user_id) == row.id,
                )
                nodes.append(node)
                rels.extend(row_rels)

            except (TransformationError, CanonicalizationError) as exc:
                self._skip(str(exc), row_id=getattr(row, "id", None))
                continue

        log_transformation_finished(
            self._logger,
            record_count=len(nodes) + len(rels),
            table_name=SOURCE_NAME,
            run_id=self._run_id,
        )

        return builder.batch(nodes, rels, batch_sequence=0)

    # -- Latest snapshot resolution -------------------------------------------

    def _find_latest_per_user(self, rows: list) -> dict[str, int]:
        """
        Return a dict mapping user_id → source row id for the row with the
        maximum last_calculated_at per user.

        When two rows share the same last_calculated_at for the same user,
        the lower source row id is used as a deterministic tiebreaker.

        Args:
            rows: List of UserBehaviorRow instances from the batch.

        Returns:
            Dict of {user_id: row.id} for the latest snapshot per user.
        """
        latest: dict[str, tuple[datetime | None, int]] = {}

        for row in rows:
            row: UserBehaviorRow
            if not row.user_id:
                continue

            current = latest.get(row.user_id)

            if current is None:
                latest[row.user_id] = (row.last_calculated_at, row.id)
                continue

            current_dt, current_id = current

            # Compare datetimes — None sorts last (treated as oldest)
            if row.last_calculated_at is None:
                continue
            if current_dt is None or row.last_calculated_at > current_dt:
                latest[row.user_id] = (row.last_calculated_at, row.id)
            elif row.last_calculated_at == current_dt and row.id < current_id:
                # Tiebreak: lower source id wins
                latest[row.user_id] = (row.last_calculated_at, row.id)

        return {user_id: row_id for user_id, (_, row_id) in latest.items()}

    # -- Row-level transform --------------------------------------------------

    def _transform_row(
        self,
        row: UserBehaviorRow,
        builder: GraphRecordBuilder,
        *,
        is_current: bool,
    ) -> tuple[NodeRecord, list[RelationshipRecord]]:
        node_id = build_persona_state_snapshot_key(
            row.user_id,
            row.behaviour_label,
            row.last_calculated_at,
        )
        user_node_id = build_user_id(row.user_id)

        candidates = {
            "user_id":             row.user_id,
            "pcm_stage":           row.pcm_stage,
            "behaviour_label":     row.behaviour_label,
            "birfing_coefficient": row.birfing_coefficient,
            "frustration_bias":    row.frustration_bias,
            "calculated_at":       self._ts(row.last_calculated_at),
        }

        properties = {
            key: value
            for key, value in candidates.items()
            if may_source_write_property(SOURCE_NAME, "PersonaState", key)
        }

        node = builder.node(PERSONA_STATE, node_id, properties)

        row_rels: list[RelationshipRecord] = []

        if is_current:
            row_rels.append(
                builder.rel(
                    CURRENT_STATE,
                    user_node_id,
                    node_id,
                    start_label=USER,
                    end_label=PERSONA_STATE,
                )
            )

        return node, row_rels