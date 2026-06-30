"""
app/transformers/gamification.py
=================================
Transformer for five gamification sources → Poll, Question, Quiz,
and QuizQuestion nodes.

Dispatches on batch.source_name:
    "dim_fixture_polls_enhanced" → Poll nodes
    "dim_questions"              → Question nodes (core properties)
    "dim_questions_enhanced"     → Question nodes (enrichment properties)
    "dim_quizzes"                → Quiz nodes
    "dim_quiz_questions_enhanced" → QuizQuestion nodes

Question enrichment:
    dim_questions and dim_questions_enhanced both produce NodeRecord with
    label=Question and the same node id. Property authority is enforced
    via may_source_write_property() per source. The loader's MERGE query
    handles the graph-level property merge — no in-memory merge needed
    since batches arrive separately.

No relationships emitted from this transformer.
ANSWERED (User → Poll) is written by activities.py.
"""

from __future__ import annotations

from app.contracts.graph_records import GraphWriteBatch, NodeRecord
from app.contracts.warehouse_rows import ExtractorBatch
from app.core.constants import POLL, QUESTION, QUIZ, QUIZ_QUESTION
from app.core.exceptions import CanonicalizationError, TransformationError
from app.core.ids import (
    build_poll_id,
    build_question_id,
    build_quiz_id,
    build_quiz_question_id,
)
from app.core.logging import log_transformation_finished, log_transformation_started
from app.mappings.property_ownership import may_source_write_property
from app.schemas.warehouse.fixture_polls import (
    INCLUSION_MODE,
    SOURCE_NAME as POLLS_SOURCE_NAME,
    FixturePollsRow,
)
from app.schemas.warehouse.questions import (
    SOURCE_NAME as QUESTIONS_SOURCE_NAME,
    QuestionsRow,
)
from app.schemas.warehouse.questions_enhanced import (
    SOURCE_NAME as QUESTIONS_ENHANCED_SOURCE_NAME,
    QuestionsEnhancedRow,
)
from app.schemas.warehouse.quiz_questions import (
    SOURCE_NAME as QUIZ_QUESTIONS_SOURCE_NAME,
    QuizQuestionsRow,
)
from app.schemas.warehouse.quizzes import (
    SOURCE_NAME as QUIZZES_SOURCE_NAME,
    QuizzesRow,
)
from app.transformers.base import BaseTransformer
from app.transformers.graph_record_builder import GraphRecordBuilder


class GamificationTransformer(BaseTransformer):
    """
    Transforms five gamification sources into Poll, Question, Quiz,
    and QuizQuestion node records.

    Registered under dim_fixture_polls_enhanced as the primary source.
    The pipeline must route all five sources here.
    """

    source_name = POLLS_SOURCE_NAME   # "dim_fixture_polls_enhanced"
    secondary_sources = (QUESTIONS_SOURCE_NAME, QUESTIONS_ENHANCED_SOURCE_NAME, QUIZZES_SOURCE_NAME, QUIZ_QUESTIONS_SOURCE_NAME)
    inclusion_mode = INCLUSION_MODE    # GRAPH_CORE

    def transform(self, batch: ExtractorBatch) -> GraphWriteBatch:
        if batch.source_name == POLLS_SOURCE_NAME:
            return self._transform_polls(batch)
        if batch.source_name == QUESTIONS_SOURCE_NAME:
            return self._transform_questions(batch)
        if batch.source_name == QUESTIONS_ENHANCED_SOURCE_NAME:
            return self._transform_questions_enhanced(batch)
        if batch.source_name == QUIZZES_SOURCE_NAME:
            return self._transform_quizzes(batch)
        if batch.source_name == QUIZ_QUESTIONS_SOURCE_NAME:
            return self._transform_quiz_questions(batch)
        raise TransformationError(
            f"GamificationTransformer received unexpected source '{batch.source_name}'",
            source=batch.source_name,
        )

    # -- Poll nodes -----------------------------------------------------------

    def _transform_polls(self, batch: ExtractorBatch) -> GraphWriteBatch:
        self._reset_skip_count()
        builder = GraphRecordBuilder(self._run_id, POLLS_SOURCE_NAME)
        nodes: list[NodeRecord] = []

        log_transformation_started(self._logger, table_name=POLLS_SOURCE_NAME, run_id=self._run_id)

        for row in batch.rows:
            row: FixturePollsRow
            try:
                if not row.fixture_poll_id:
                    raise TransformationError("Missing fixture_poll_id", source=POLLS_SOURCE_NAME)

                node_id = build_poll_id(row.fixture_poll_id)
                properties = {
                    "fixture_id":        row.fixture_id,
                    "creator_user_id":   row.creator_user_id,
                    "question_text":     row.question_text,
                    "option1":           row.option1,
                    "option2":           row.option2,
                    "created_at":        self._ts(row.created_at_utc),
                    "is_active":         self._bool(row.is_active),
                    "total_responses":   row.total_responses,
                }
                nodes.append(builder.node(POLL, node_id, properties))
            except (TransformationError, CanonicalizationError) as exc:
                self._skip(str(exc), row_id=getattr(row, "fixture_poll_id", None))

        log_transformation_finished(self._logger, record_count=len(nodes), table_name=POLLS_SOURCE_NAME, run_id=self._run_id)
        return builder.batch(nodes, [], batch_sequence=0)

    # -- Question nodes (core) ------------------------------------------------

    def _transform_questions(self, batch: ExtractorBatch) -> GraphWriteBatch:
        self._reset_skip_count()
        builder = GraphRecordBuilder(self._run_id, QUESTIONS_SOURCE_NAME)
        nodes: list[NodeRecord] = []

        log_transformation_started(self._logger, table_name=QUESTIONS_SOURCE_NAME, run_id=self._run_id)

        for row in batch.rows:
            row: QuestionsRow
            try:
                if row.question_id is None:
                    raise TransformationError("Missing question_id", source=QUESTIONS_SOURCE_NAME)

                node_id = build_question_id(row.question_id)
                candidates = {
                    "question_text": row.question_text,
                    "created_at":    self._ts(row.created_at_utc),
                }
                properties = {
                    k: v for k, v in candidates.items()
                    if may_source_write_property(QUESTIONS_SOURCE_NAME, "Question", k)
                }
                nodes.append(builder.node(QUESTION, node_id, properties))
            except (TransformationError, CanonicalizationError) as exc:
                self._skip(str(exc), row_id=getattr(row, "question_id", None))

        log_transformation_finished(self._logger, record_count=len(nodes), table_name=QUESTIONS_SOURCE_NAME, run_id=self._run_id)
        return builder.batch(nodes, [], batch_sequence=0)

    # -- Question nodes (enrichment) ------------------------------------------

    def _transform_questions_enhanced(self, batch: ExtractorBatch) -> GraphWriteBatch:
        self._reset_skip_count()
        builder = GraphRecordBuilder(self._run_id, QUESTIONS_ENHANCED_SOURCE_NAME)
        nodes: list[NodeRecord] = []

        log_transformation_started(self._logger, table_name=QUESTIONS_ENHANCED_SOURCE_NAME, run_id=self._run_id)

        for row in batch.rows:
            row: QuestionsEnhancedRow
            try:
                if row.question_id is None:
                    raise TransformationError("Missing question_id", source=QUESTIONS_ENHANCED_SOURCE_NAME)

                node_id = build_question_id(row.question_id)
                candidates = {
                    "question_title":         row.question_title,
                    "total_responses":         row.total_responses,
                    "yes_percentage":          row.yes_percentage,
                    "no_percentage":           row.no_percentage,
                    "last_response_at":        self._ts(row.last_response_at_utc),
                    "avg_response_time_minutes": row.avg_response_time_minutes,
                }
                properties = {
                    k: v for k, v in candidates.items()
                    if may_source_write_property(QUESTIONS_ENHANCED_SOURCE_NAME, "Question", k)
                }
                nodes.append(builder.node(QUESTION, node_id, properties))
            except (TransformationError, CanonicalizationError) as exc:
                self._skip(str(exc), row_id=getattr(row, "question_id", None))

        log_transformation_finished(self._logger, record_count=len(nodes), table_name=QUESTIONS_ENHANCED_SOURCE_NAME, run_id=self._run_id)
        return builder.batch(nodes, [], batch_sequence=0)

    # -- Quiz nodes -----------------------------------------------------------

    def _transform_quizzes(self, batch: ExtractorBatch) -> GraphWriteBatch:
        self._reset_skip_count()
        builder = GraphRecordBuilder(self._run_id, QUIZZES_SOURCE_NAME)
        nodes: list[NodeRecord] = []

        log_transformation_started(self._logger, table_name=QUIZZES_SOURCE_NAME, run_id=self._run_id)

        for row in batch.rows:
            row: QuizzesRow
            try:
                if row.quiz_id is None:
                    raise TransformationError("Missing quiz_id", source=QUIZZES_SOURCE_NAME)

                node_id = build_quiz_id(row.quiz_id)
                properties = {
                    "quiz_name":       row.quiz_name,
                    "creator_user_id": row.creator_user_id,
                    "created_at":      self._ts(row.created_at_utc),
                    "scheduled_date":  self._ts(row.scheduled_date),
                    "total_questions": row.total_questions,
                    "is_active":       self._bool(row.is_active),
                }
                nodes.append(builder.node(QUIZ, node_id, properties))
            except (TransformationError, CanonicalizationError) as exc:
                self._skip(str(exc), row_id=getattr(row, "quiz_id", None))

        log_transformation_finished(self._logger, record_count=len(nodes), table_name=QUIZZES_SOURCE_NAME, run_id=self._run_id)
        return builder.batch(nodes, [], batch_sequence=0)

    # -- QuizQuestion nodes ---------------------------------------------------

    def _transform_quiz_questions(self, batch: ExtractorBatch) -> GraphWriteBatch:
        self._reset_skip_count()
        builder = GraphRecordBuilder(self._run_id, QUIZ_QUESTIONS_SOURCE_NAME)
        nodes: list[NodeRecord] = []

        log_transformation_started(self._logger, table_name=QUIZ_QUESTIONS_SOURCE_NAME, run_id=self._run_id)

        for row in batch.rows:
            row: QuizQuestionsRow
            try:
                if row.quiz_question_id is None:
                    raise TransformationError("Missing quiz_question_id", source=QUIZ_QUESTIONS_SOURCE_NAME)

                node_id = build_quiz_question_id(row.quiz_question_id)
                properties = {
                    "question_text":    row.question_text,
                    "correct_option":   row.correct_option,
                    "difficulty_level": row.difficulty_level,
                    "total_attempts":   row.total_attempts,
                    "accuracy_rate":    row.accuracy_rate,   # float — stays float per plan
                    "created_at":       self._ts(row.created_at_utc),
                    "is_active":        self._bool(row.is_active),
                }
                nodes.append(builder.node(QUIZ_QUESTION, node_id, properties))
            except (TransformationError, CanonicalizationError) as exc:
                self._skip(str(exc), row_id=getattr(row, "quiz_question_id", None))

        log_transformation_finished(self._logger, record_count=len(nodes), table_name=QUIZ_QUESTIONS_SOURCE_NAME, run_id=self._run_id)
        return builder.batch(nodes, [], batch_sequence=0)