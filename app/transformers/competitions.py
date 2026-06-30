"""
app/transformers/competitions.py
=================================
Transformer for four competition sources → Super6Round nodes,
LMSCompetition nodes, HAS_FIXTURE rels, and PARTICIPATED_IN rels.

Dispatches on batch.source_name:
    "dim_super6_rounds"         → Super6Round nodes
    "dim_lms_competitions"      → LMSCompetition nodes + PARTICIPATED_IN
                                   (User → LMSCompetition) via created_by_user_id
    "dim_super6_round_fixtures" → HAS_FIXTURE rels (Super6Round → Match)
    "fct_super6_participants"   → PARTICIPATED_IN rels (User → Super6Round)

HAS_FIXTURE start endpoint: CompetitionCanonicalizer.resolve_super6_round
PARTICIPATED_IN (Super6) end endpoint: CompetitionCanonicalizer.resolve_super6_round
PARTICIPATED_IN (LMS) end endpoint: CompetitionCanonicalizer.resolve_lms_competition
All via self._resolve_endpoint() — no direct canonicalizer calls.
"""

from __future__ import annotations

from app.contracts.graph_records import GraphWriteBatch, NodeRecord, RelationshipRecord
from app.contracts.warehouse_rows import ExtractorBatch
from app.core.constants import (
    HAS_FIXTURE,
    LMS_COMPETITION,
    MATCH,
    PARTICIPATED_IN,
    SUPER6_ROUND,
    USER,
)
from app.core.exceptions import CanonicalizationError, TransformationError
from app.core.ids import (
    build_fixture_id,
    build_lms_competition_id,
    build_super6_round_id,
    build_user_id,
)
from app.core.logging import log_transformation_finished, log_transformation_started
from app.mappings.registry import MappingRegistry
from app.schemas.warehouse.lms_competitions import (
    SOURCE_NAME as LMS_SOURCE_NAME,
    LmsCompetitionsRow,
)
from app.schemas.warehouse.super6_participants import (
    SOURCE_NAME as PARTICIPANTS_SOURCE_NAME,
    Super6ParticipantsRow,
)
from app.schemas.warehouse.super6_round_fixtures import (
    SOURCE_NAME as FIXTURES_SOURCE_NAME,
    Super6RoundFixturesRow,
)
from app.schemas.warehouse.super6_rounds import (
    INCLUSION_MODE,
    SOURCE_NAME as ROUNDS_SOURCE_NAME,
    Super6RoundsRow,
)
from app.transformers.base import BaseTransformer
from app.transformers.graph_record_builder import GraphRecordBuilder

_ALL_SOURCES = frozenset({
    ROUNDS_SOURCE_NAME,
    LMS_SOURCE_NAME,
    FIXTURES_SOURCE_NAME,
    PARTICIPANTS_SOURCE_NAME,
})


class CompetitionsTransformer(BaseTransformer):
    """
    Transforms four competition sources into competition graph records.

    Registered under dim_super6_rounds as the primary source.
    The pipeline must route all four sources here.
    """

    source_name = ROUNDS_SOURCE_NAME   # "dim_super6_rounds"
    secondary_sources = (LMS_SOURCE_NAME, FIXTURES_SOURCE_NAME, PARTICIPANTS_SOURCE_NAME)
    inclusion_mode = INCLUSION_MODE    # GRAPH_CORE

    def transform(self, batch: ExtractorBatch) -> GraphWriteBatch:
        if batch.source_name == ROUNDS_SOURCE_NAME:
            return self._transform_super6_rounds(batch)
        if batch.source_name == LMS_SOURCE_NAME:
            return self._transform_lms_competitions(batch)
        if batch.source_name == FIXTURES_SOURCE_NAME:
            return self._transform_round_fixtures(batch)
        if batch.source_name == PARTICIPANTS_SOURCE_NAME:
            return self._transform_super6_participants(batch)
        raise TransformationError(
            f"CompetitionsTransformer received unexpected source '{batch.source_name}'",
            source=batch.source_name,
        )

    # -- Super6Round nodes ----------------------------------------------------

    def _transform_super6_rounds(self, batch: ExtractorBatch) -> GraphWriteBatch:
        self._reset_skip_count()
        builder = GraphRecordBuilder(self._run_id, ROUNDS_SOURCE_NAME)
        nodes: list[NodeRecord] = []

        log_transformation_started(self._logger, table_name=ROUNDS_SOURCE_NAME, run_id=self._run_id)

        for row in batch.rows:
            row: Super6RoundsRow
            try:
                if not row.super6_round_id:
                    raise TransformationError("Missing super6_round_id", source=ROUNDS_SOURCE_NAME)

                node_id = build_super6_round_id(row.super6_round_id)
                properties = {
                    "round_number":   row.round_number,
                    "start_date":     self._ts(row.start_date_utc),
                    "end_date":       self._ts(row.end_date_utc),
                    "is_active":      self._bool(row.is_active),
                    "created_at":     self._ts(row.created_at_utc),
                }
                nodes.append(builder.node(SUPER6_ROUND, node_id, properties))
            except (TransformationError, CanonicalizationError) as exc:
                self._skip(str(exc), row_id=getattr(row, "super6_round_id", None))

        log_transformation_finished(self._logger, record_count=len(nodes), table_name=ROUNDS_SOURCE_NAME, run_id=self._run_id)
        return builder.batch(nodes, [], batch_sequence=0)

    # -- LMSCompetition nodes + PARTICIPATED_IN rels --------------------------

    def _transform_lms_competitions(self, batch: ExtractorBatch) -> GraphWriteBatch:
        self._reset_skip_count()
        builder = GraphRecordBuilder(self._run_id, LMS_SOURCE_NAME)
        nodes: list[NodeRecord] = []
        rels: list[RelationshipRecord] = []

        log_transformation_started(self._logger, table_name=LMS_SOURCE_NAME, run_id=self._run_id)

        for row in batch.rows:
            row: LmsCompetitionsRow
            try:
                if not row.lms_competition_id:
                    raise TransformationError("Missing lms_competition_id", source=LMS_SOURCE_NAME)

                node_id = build_lms_competition_id(row.lms_competition_id)
                properties = {
                    "competition_name":      row.competition_name,
                    "status":                row.status,
                    "season_year":           row.season_year,
                    "entry_fee_coins":       row.entry_fee_coins,
                    "prize_pool_coins":      row.prize_pool_coins,
                    "max_participants":      row.max_participants,
                    "current_participants":  row.current_participants,
                    "survivors_remaining":   row.survivors_remaining,
                    "elimination_rule":      row.elimination_rule,
                    "winner_user_id":        row.winner_user_id,
                    "created_at":            self._ts(row.created_at),
                    "completed_at":          self._ts(row.completed_at),
                }
                nodes.append(builder.node(LMS_COMPETITION, node_id, properties))

                # PARTICIPATED_IN from created_by_user_id
                if row.created_by_user_id:
                    try:
                        lms_end_id = self._resolve_endpoint(
                            PARTICIPATED_IN, "end", row.lms_competition_id,
                            source_name=LMS_SOURCE_NAME,
                        )
                        if lms_end_id:
                            rels.append(builder.rel(
                                PARTICIPATED_IN,
                                build_user_id(row.created_by_user_id),
                                lms_end_id,
                                start_label=USER,
                                end_label=LMS_COMPETITION,
                                properties={"joined_at": self._ts(row.created_at)},
                            ))
                    except TransformationError as exc:
                        self._skip(str(exc), row_id=row.lms_competition_id, rel=PARTICIPATED_IN)

            except (TransformationError, CanonicalizationError) as exc:
                self._skip(str(exc), row_id=getattr(row, "lms_competition_id", None))

        log_transformation_finished(self._logger, record_count=len(nodes) + len(rels), table_name=LMS_SOURCE_NAME, run_id=self._run_id)
        return builder.batch(nodes, rels, batch_sequence=0)

    # -- HAS_FIXTURE rels -----------------------------------------------------

    def _transform_round_fixtures(self, batch: ExtractorBatch) -> GraphWriteBatch:
        self._reset_skip_count()
        builder = GraphRecordBuilder(self._run_id, FIXTURES_SOURCE_NAME)
        rels: list[RelationshipRecord] = []

        log_transformation_started(self._logger, table_name=FIXTURES_SOURCE_NAME, run_id=self._run_id)

        for row in batch.rows:
            row: Super6RoundFixturesRow
            try:
                if not row.super6_round_id:
                    self._skip("super6_round_id is None — skipping HAS_FIXTURE rel", row_id=row.super6_round_fixture_id)
                    continue
                if not row.fixture_id:
                    self._skip("fixture_id is None — skipping HAS_FIXTURE rel", row_id=row.super6_round_fixture_id)
                    continue

                start_id = self._resolve_endpoint(HAS_FIXTURE, "start", row.super6_round_id, source_name=FIXTURES_SOURCE_NAME)
                if start_id is None:
                    continue

                rels.append(builder.rel(
                    HAS_FIXTURE,
                    start_id,
                    build_fixture_id(row.fixture_id),
                    start_label=SUPER6_ROUND,
                    end_label=MATCH,
                ))
            except (TransformationError, CanonicalizationError) as exc:
                self._skip(str(exc), row_id=getattr(row, "super6_round_fixture_id", None))

        log_transformation_finished(self._logger, record_count=len(rels), table_name=FIXTURES_SOURCE_NAME, run_id=self._run_id)
        return builder.batch([], rels, batch_sequence=0)

    # -- PARTICIPATED_IN rels (Super6) ----------------------------------------

    def _transform_super6_participants(self, batch: ExtractorBatch) -> GraphWriteBatch:
        self._reset_skip_count()
        builder = GraphRecordBuilder(self._run_id, PARTICIPANTS_SOURCE_NAME)
        rels: list[RelationshipRecord] = []

        log_transformation_started(self._logger, table_name=PARTICIPANTS_SOURCE_NAME, run_id=self._run_id)

        for row in batch.rows:
            row: Super6ParticipantsRow
            try:
                if not row.user_id:
                    self._skip("user_id is None — skipping PARTICIPATED_IN rel", row_id=row.super6_participant_id)
                    continue
                if not row.super6_round_id:
                    self._skip("super6_round_id is None — skipping PARTICIPATED_IN rel", row_id=row.super6_participant_id)
                    continue

                end_id = self._resolve_endpoint(PARTICIPATED_IN, "end", row.super6_round_id, source_name=PARTICIPANTS_SOURCE_NAME)
                if end_id is None:
                    continue

                rels.append(builder.rel(
                    PARTICIPATED_IN,
                    build_user_id(row.user_id),
                    end_id,
                    start_label=USER,
                    end_label=SUPER6_ROUND,
                    properties={
                        "super6_participant_id": row.super6_participant_id,
                        "joined_at":             self._ts(row.joined_at_utc),
                        "total_points":          row.total_points,
                        "is_winner":             self._bool(row.is_winner),
                    },
                ))
            except (TransformationError, CanonicalizationError) as exc:
                self._skip(str(exc), row_id=getattr(row, "super6_participant_id", None))

        log_transformation_finished(self._logger, record_count=len(rels), table_name=PARTICIPANTS_SOURCE_NAME, run_id=self._run_id)
        return builder.batch([], rels, batch_sequence=0)