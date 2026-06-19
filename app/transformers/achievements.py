"""
app/transformers/achievements.py
==================================
Transformer for fct_awards_and_achievements → Achievement nodes + ACHIEVED rels.

Emits:
    - Achievement node (one per row)
    - ACHIEVED rel (User → Achievement) when user_id is present

Merge key note:
    The graph field is "achievement_id" but the row field is "award_id".
    build_achievement_id(row.award_id) is the correct id construction.

reward_amount is DOUBLE on the row → self._int() coercion per universal rules.
"""

from __future__ import annotations

from app.contracts.graph_records import GraphWriteBatch, NodeRecord, RelationshipRecord
from app.contracts.warehouse_rows import ExtractorBatch
from app.core.constants import ACHIEVED, ACHIEVEMENT, USER
from app.core.exceptions import CanonicalizationError, TransformationError
from app.core.ids import build_achievement_id, build_user_id
from app.core.logging import log_transformation_finished, log_transformation_started
from app.schemas.warehouse.awards_and_achievements import (
    INCLUSION_MODE,
    SOURCE_NAME,
    AwardsAndAchievementsRow,
)
from app.transformers.base import BaseTransformer
from app.transformers.graph_record_builder import GraphRecordBuilder


class AchievementsTransformer(BaseTransformer):
    """
    Transforms fct_awards_and_achievements rows into Achievement nodes and
    ACHIEVED relationship records.

    Merge key strategy: direct on award_id (maps to graph field achievement_id).
    Node id: build_achievement_id(row.award_id)
    """

    source_name = SOURCE_NAME        # "fct_awards_and_achievements"
    inclusion_mode = INCLUSION_MODE  # GRAPH_CORE

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

        for row in batch.rows:
            row: AwardsAndAchievementsRow
            try:
                node, achieved_rel = self._transform_row(row, builder)
                nodes.append(node)
                if achieved_rel is not None:
                    rels.append(achieved_rel)
            except (TransformationError, CanonicalizationError) as exc:
                self._skip(str(exc), row_id=getattr(row, "award_id", None))
                continue

        log_transformation_finished(
            self._logger,
            record_count=len(nodes) + len(rels),
            table_name=SOURCE_NAME,
            run_id=self._run_id,
        )

        return builder.batch(nodes, rels, batch_sequence=0)

    # -- Row-level transform --------------------------------------------------

    def _transform_row(
        self,
        row: AwardsAndAchievementsRow,
        builder: GraphRecordBuilder,
    ) -> tuple[NodeRecord, RelationshipRecord | None]:
        if not row.award_id:
            raise TransformationError(
                "AwardsAndAchievementsRow missing required award_id",
                source=SOURCE_NAME,
            )

        node_id = build_achievement_id(row.award_id)

        properties = {
            "achievement_type": row.achievement_type,
            "badge_name":       row.badge_name,
            "trophy_name":      row.trophy_name,
            "reward_amount":    self._int(row.reward_amount),
            "earned_at":        self._ts(row.earned_at_utc),
        }

        node = builder.node(ACHIEVEMENT, node_id, properties)

        achieved_rel = None
        if row.user_id:
            achieved_rel = builder.rel(
                ACHIEVED,
                build_user_id(row.user_id),
                node_id,
                start_label=USER,
                end_label=ACHIEVEMENT,
                properties={"earned_at": self._ts(row.earned_at_utc)},
            )
        else:
            self._skip(
                "user_id is None — skipping ACHIEVED rel",
                row_id=row.award_id,
            )

        return node, achieved_rel