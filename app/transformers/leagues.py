"""
app/transformers/leagues.py
============================
Transformer for dim_leagues → League nodes.

Emits League nodes only. No relationships are emitted here.
IN_LEAGUE (Match → League) is written by fixtures.py.
PLAYS_IN  (Team → League) is not currently emitted by any transformer
          (league_id is not present on TeamsRow).
"""

from __future__ import annotations

from app.contracts.graph_records import GraphWriteBatch, NodeRecord
from app.contracts.warehouse_rows import ExtractorBatch
from app.core.constants import LEAGUE
from app.core.exceptions import CanonicalizationError, TransformationError
from app.core.ids import build_league_id
from app.core.logging import log_transformation_finished, log_transformation_started
from app.schemas.warehouse.leagues import INCLUSION_MODE, SOURCE_NAME, LeaguesRow
from app.transformers.base import BaseTransformer
from app.transformers.graph_record_builder import GraphRecordBuilder


class LeaguesTransformer(BaseTransformer):
    """
    Transforms dim_leagues rows into League nodes.

    Merge key strategy: direct on league_id (declared in merge_keys.py).
    Node id:           build_league_id(row.league_id) — league_id is int on row.
    Relationships:     none emitted here.
    """

    source_name = SOURCE_NAME        # "dim_leagues"
    inclusion_mode = INCLUSION_MODE  # GRAPH_CORE

    def transform(self, batch: ExtractorBatch) -> GraphWriteBatch:
        """
        Transform a batch of LeaguesRow instances into League node records.

        Args:
            batch: ExtractorBatch from the dim_leagues extractor.

        Returns:
            GraphWriteBatch containing League NodeRecord instances.
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
            row: LeaguesRow
            try:
                nodes.append(self._transform_row(row, builder))
            except (TransformationError, CanonicalizationError) as exc:
                self._skip(str(exc), row_id=getattr(row, "league_id", None))
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
        row: LeaguesRow,
        builder: GraphRecordBuilder,
    ) -> NodeRecord:
        """
        Transform a single LeaguesRow into a League NodeRecord.

        Fields mapped to LeagueNode shape:
            league_name, country, season, league_logo, is_active

        Fields present on LeaguesRow but excluded (not in LeagueNode shape):
            country_code, country_flag, created_at, updated_at

        Args:
            row:     Typed LeaguesRow instance.
            builder: GraphRecordBuilder pre-filled with run_id and source.

        Returns:
            Validated League NodeRecord.

        Raises:
            TransformationError: If league_id is missing.
        """
        if row.league_id is None:
            raise TransformationError(
                "LeaguesRow missing required league_id",
                source=SOURCE_NAME,
            )

        node_id = build_league_id(row.league_id)

        properties = {
            "league_name": row.league_name,
            "country":     row.country,
            "season":      row.season,
            "league_logo": row.league_logo,
            "is_active":   self._bool(row.is_active),
        }

        return builder.node(LEAGUE, node_id, properties)