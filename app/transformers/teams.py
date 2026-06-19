"""
app/transformers/teams.py
==========================
Transformer for dim_teams + dim_teams_enhanced → Team nodes.

Handles two sources in one transformer. Dispatches on batch.source_name:

    dim_teams          → base Team node with identity and core properties
    dim_teams_enhanced → enrichment Team node with fan analytics properties

Both emit NodeRecord with label=Team and the same node_id (built from
team_id). The loader's MERGE query handles property-level merging at
Neo4j write time — no in-memory merge is performed here.

Property authority per property_ownership.py:
    dim_teams owns:
        team_name (OVERWRITE), team_code (WRITE_ONCE), country (FILL_IF_NULL),
        league_id (OVERWRITE)

    dim_teams_enhanced owns:
        team_logo (FILL_IF_NULL), total_fans (OVERWRITE), fan_rank (OVERWRITE),
        fan_engagement_score (OVERWRITE), fan_growth_rate (OVERWRITE)

    venue_name has no ownership spec → excluded by may_source_write_property.

No relationships are emitted from this transformer.
PLAYS_IN (Team → League) is declared in ENDPOINT_SPECS but is written
by the fixtures pipeline, not here.
"""

from __future__ import annotations

from app.contracts.graph_records import GraphWriteBatch, NodeRecord
from app.contracts.warehouse_rows import ExtractorBatch
from app.core.constants import TEAM
from app.core.exceptions import CanonicalizationError, TransformationError
from app.core.ids import build_team_id
from app.core.logging import log_transformation_finished, log_transformation_started
from app.mappings.property_ownership import may_source_write_property
from app.schemas.warehouse.teams import (
    INCLUSION_MODE as TEAMS_INCLUSION_MODE,
    SOURCE_NAME as TEAMS_SOURCE_NAME,
    TeamsRow,
)
from app.schemas.warehouse.teams_enhanced import (
    SOURCE_NAME as ENHANCED_SOURCE_NAME,
    TeamsEnhancedRow,
)
from app.transformers.base import BaseTransformer
from app.transformers.graph_record_builder import GraphRecordBuilder

# This transformer is registered under the base source name.
# The pipeline must also route dim_teams_enhanced batches here.
_BASE_SOURCE_NAME = TEAMS_SOURCE_NAME        # "dim_teams"
_ENHANCED_SOURCE_NAME = ENHANCED_SOURCE_NAME  # "dim_teams_enhanced"


class TeamsTransformer(BaseTransformer):
    """
    Transforms dim_teams and dim_teams_enhanced rows into Team nodes.

    Registered under dim_teams as the primary source. The pipeline must
    route dim_teams_enhanced batches to this transformer's
    transform_enhanced() method, or call transform() with the enhanced
    batch (dispatch happens on batch.source_name).

    Merge key strategy: direct on team_id for both sources.
    Node id:           build_team_id(row.team_id) — handles int and str.
    Relationships:     none emitted here.
    """

    source_name = _BASE_SOURCE_NAME
    inclusion_mode = TEAMS_INCLUSION_MODE  # GRAPH_CORE

    def transform(self, batch: ExtractorBatch) -> GraphWriteBatch:
        """
        Transform a batch of Team rows into Team node records.

        Dispatches on batch.source_name:
            "dim_teams"          → _transform_base_batch()
            "dim_teams_enhanced" → _transform_enhanced_batch()

        Args:
            batch: ExtractorBatch from dim_teams or dim_teams_enhanced.

        Returns:
            GraphWriteBatch containing Team NodeRecord instances.

        Raises:
            TransformationError: If batch.source_name is not a recognised
                team source.
        """
        if batch.source_name == _BASE_SOURCE_NAME:
            return self._transform_base_batch(batch)

        if batch.source_name == _ENHANCED_SOURCE_NAME:
            return self._transform_enhanced_batch(batch)

        raise TransformationError(
            f"TeamsTransformer received unexpected source '{batch.source_name}'. "
            f"Expected '{_BASE_SOURCE_NAME}' or '{_ENHANCED_SOURCE_NAME}'.",
            source=batch.source_name,
        )

    # -- Base source (dim_teams) ----------------------------------------------

    def _transform_base_batch(self, batch: ExtractorBatch) -> GraphWriteBatch:
        self._reset_skip_count()
        builder = GraphRecordBuilder(self._run_id, _BASE_SOURCE_NAME)
        nodes: list[NodeRecord] = []

        log_transformation_started(
            self._logger,
            table_name=_BASE_SOURCE_NAME,
            run_id=self._run_id,
        )

        for row in batch.rows:
            row: TeamsRow
            try:
                nodes.append(self._transform_base_row(row, builder))
            except (TransformationError, CanonicalizationError) as exc:
                self._skip(str(exc), row_id=getattr(row, "team_id", None))
                continue

        log_transformation_finished(
            self._logger,
            record_count=len(nodes),
            table_name=_BASE_SOURCE_NAME,
            run_id=self._run_id,
        )

        return builder.batch(nodes, [], batch_sequence=0)

    def _transform_base_row(
        self,
        row: TeamsRow,
        builder: GraphRecordBuilder,
    ) -> NodeRecord:
        if not row.team_id:
            raise TransformationError(
                "TeamsRow missing required team_id",
                source=_BASE_SOURCE_NAME,
            )

        node_id = build_team_id(row.team_id)

        # venue_name has no ownership spec in property_ownership.py → excluded by filter.
        # league_id is not a field on TeamsRow (it lives on TeamsEnhancedRow).
        properties = {
            key: value
            for key, value in {
                "team_name":  row.team_name,
                "team_code":  row.team_code,
                "country":    row.country,
                "venue_name": row.venue_name,
            }.items()
            if may_source_write_property(_BASE_SOURCE_NAME, "Team", key)
        }

        return builder.node(TEAM, node_id, properties)

    # -- Enhanced source (dim_teams_enhanced) ---------------------------------

    def _transform_enhanced_batch(self, batch: ExtractorBatch) -> GraphWriteBatch:
        self._reset_skip_count()
        builder = GraphRecordBuilder(self._run_id, _ENHANCED_SOURCE_NAME)
        nodes: list[NodeRecord] = []

        log_transformation_started(
            self._logger,
            table_name=_ENHANCED_SOURCE_NAME,
            run_id=self._run_id,
        )

        for row in batch.rows:
            row: TeamsEnhancedRow
            try:
                nodes.append(self._transform_enhanced_row(row, builder))
            except (TransformationError, CanonicalizationError) as exc:
                self._skip(str(exc), row_id=getattr(row, "team_id", None))
                continue

        log_transformation_finished(
            self._logger,
            record_count=len(nodes),
            table_name=_ENHANCED_SOURCE_NAME,
            run_id=self._run_id,
        )

        return builder.batch(nodes, [], batch_sequence=0)

    def _transform_enhanced_row(
        self,
        row: TeamsEnhancedRow,
        builder: GraphRecordBuilder,
    ) -> NodeRecord:
        if row.team_id is None:
            raise TransformationError(
                "TeamsEnhancedRow missing required team_id",
                source=_ENHANCED_SOURCE_NAME,
            )

        # team_id is int on TeamsEnhancedRow — build_team_id normalizes to str
        node_id = build_team_id(row.team_id)

        candidates = {
            "team_logo":            row.team_logo,
            "total_fans":           row.total_fans,
            "fan_rank":             row.fan_rank,
            "fan_engagement_score": row.fan_engagement_score,
            "fan_growth_rate":      row.fan_growth_rate,
        }

        properties = {
            key: value
            for key, value in candidates.items()
            if may_source_write_property(_ENHANCED_SOURCE_NAME, "Team", key)
        }

        return builder.node(TEAM, node_id, properties)