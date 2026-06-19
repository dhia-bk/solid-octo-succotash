"""
Competition pipeline — predictions, duels, Super6, LMS, polls, questions, quizzes.

fct_predictions first — highest volume source, benefits from early dedicated batch.
FK ordering: round nodes before round-fixture junctions,
question core before question enrichment.

Requires identity_pipeline (User) and sports_pipeline (Match for PREDICTED rels).
"""

from __future__ import annotations

from app.core.constants import COMPETITION_PIPELINE
from app.pipelines.base import BasePipeline


class CompetitionPipeline(BasePipeline):
    """
    Loads competition domain: PREDICTED rels, Duel, Super6Round, LMSCompetition,
    Poll, Question, Quiz, QuizQuestion nodes and their edges.
    """

    pipeline_name = COMPETITION_PIPELINE
    sources = (
        "fct_predictions",              # PREDICTED rels — highest volume
        "fct_prediction_duels",         # Duel nodes + CHALLENGED rels
        "dim_super6_rounds",            # Super6Round nodes
        "dim_super6_round_fixtures",    # HAS_FIXTURE rels (round → match)
        "fct_super6_participants",      # PARTICIPATED_IN rels (User → Super6Round)
        "dim_lms_competitions",         # LMSCompetition nodes + PARTICIPATED_IN rels
        "dim_fixture_polls_enhanced",   # Poll nodes
        "dim_questions",                # Question nodes (core)
        "dim_questions_enhanced",       # Question enrichment — after dim_questions
        "dim_quizzes",                  # Quiz nodes
        "dim_quiz_questions_enhanced",  # QuizQuestion nodes
    )
