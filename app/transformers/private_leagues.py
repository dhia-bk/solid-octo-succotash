"""
app/transformers/private_leagues.py
=====================================
Transformer for dim_private_leagues → PrivateLeague nodes.

Full-refresh source — no watermark, no incremental logic.
Emits PrivateLeague nodes only. The MEMBER_OF relationship
(User → PrivateLeague) is written by memberships.py.

Fields on PrivateLeaguesRow excluded from PrivateLeagueNode shape:
    image, about, join_code
"""

from __future__ import annotations

from app.contracts.graph_records import GraphWriteBatch, NodeRecord
from app.contracts.warehouse_rows import ExtractorBatch
from app.core.constants import PRIVATE_LEAGUE
from app.core.exceptions import CanonicalizationError, TransformationError
from app.core.ids import build_private_league_id
from app.core.logging import log_transformation_finished, log_transformation_started
from app.schemas.warehouse.private_leagues import (
    INCLUSION_MODE,
    SOURCE_NAME,
    PrivateLeaguesRow,
)
from app.transformers.base import BaseTransformer
from app.transformers.graph_record_builder import GraphRecordBuilder


class PrivateLeaguesTransformer(BaseTransformer):
    """
    Transforms dim_private_leagues rows into PrivateLeague nodes.

    Merge key strategy: direct on private_league_id (declared in merge_keys.py).
    Node id:           build_private_league_id(row.private_league_id)
    Relationships:     none — MEMBER_OF is written by memberships.py.
    """

    source_name = SOURCE_NAME        # "dim_private_leagues"
    inclusion_mode = INCLUSION_MODE  # GRAPH_CORE

    def transform(self, batch: ExtractorBatch) -> GraphWriteBatch:
        """
        Transform a batch of PrivateLeaguesRow instances into PrivateLeague
        node records.

        Args:
            batch: ExtractorBatch from the dim_private_leagues extractor.

        Returns:
            GraphWriteBatch containing PrivateLeague NodeRecord instances.
        """
        self._reset_skip_count()
        builder = GraphRecordBuilder(self._run_id, SOURCE_NAME)
        nodes: list[NodeRecord] = []

        log_transformation_started(
            self._logger,
            table_name=SOURCE_NAME,
            run_id=self._run_id,
        )

        for row in batch.rows:
            row: PrivateLeaguesRow
            try:
                nodes.append(self._transform_row(row, builder))
            except (TransformationError, CanonicalizationError) as exc:
                self._skip(str(exc), row_id=getattr(row, "private_league_id", None))
                continue

        log_transformation_finished(
            self._logger,
            record_count=len(nodes),
            table_name=SOURCE_NAME,
            run_id=self._run_id,
        )

        return builder.batch(nodes, [], batch_sequence=0)

    # -- Row-level transform --------------------------------------------------

    def _transform_row(
        self,
        row: PrivateLeaguesRow,
        builder: GraphRecordBuilder,
    ) -> NodeRecord:
        """
        Transform a single PrivateLeaguesRow into a PrivateLeague NodeRecord.

        Args:
            row:     Typed PrivateLeaguesRow instance.
            builder: GraphRecordBuilder pre-filled with run_id and source.

        Returns:
            Validated PrivateLeague NodeRecord.

        Raises:
            TransformationError: If private_league_id is missing.
        """
        if row.private_league_id is None:
            raise TransformationError(
                "PrivateLeaguesRow missing required private_league_id",
                source=SOURCE_NAME,
            )

        node_id = build_private_league_id(row.private_league_id)

        properties = {
            "league_name":    row.league_name,
            "owner_user_id":  row.owner_user_id,
            "member_count":   row.member_count,
            "is_generic":     self._bool(row.is_generic),
        }

        return builder.node(PRIVATE_LEAGUE, node_id, properties)