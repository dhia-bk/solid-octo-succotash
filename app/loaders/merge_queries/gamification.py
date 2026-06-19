"""
Merge queries for gamification (polls, questions, quizzes).
Source(s): dim_fixture_polls, dim_questions, dim_questions_enhanced, dim_quizzes, dim_quiz_questions_enhanced
"""

from __future__ import annotations

from app.loaders.merge_queries.base import (
    build_enrichment_merge_query,
    build_node_merge_query,
)


def get_poll_merge_query(source_name: str = "dim_fixture_polls") -> str:
    """Return Cypher MERGE query for Poll nodes."""
    return build_node_merge_query(
        label="Poll",
        merge_key_field="id",
        write_once_fields=[],
        mutable_fields=[
            "question_text",
            "fixture_id",
            "option_a",
            "option_b",
            "is_active",
            "result",
            "closed_at",
        ],
    )


def get_question_merge_query(source_name: str = "dim_questions") -> str:
    """Return Cypher MERGE query for Question nodes."""
    return build_node_merge_query(
        label="Question",
        merge_key_field="id",
        write_once_fields=["created_at"],
        mutable_fields=["question_text", "question_type", "is_active"],
    )


def get_question_enrichment_merge_query(
    source_name: str = "dim_questions_enhanced",
) -> str:
    """Return Cypher enrichment query writing response stats to Question nodes."""
    return build_enrichment_merge_query(
        label="Question",
        merge_key_field="id",
        enrichment_fields=[],
        write_policy_overwrite=[
            "total_responses",
            "yes_percentage",
            "last_response_at",
        ],
        write_policy_fill_if_null=[],
    )


def get_quiz_merge_query(source_name: str = "dim_quizzes") -> str:
    """Return Cypher MERGE query for Quiz nodes."""
    return build_node_merge_query(
        label="Quiz",
        merge_key_field="id",
        write_once_fields=[],
        mutable_fields=[
            "quiz_name",
            "quiz_type",
            "question_count",
            "time_limit_seconds",
            "is_active",
        ],
    )


def get_quiz_question_merge_query(
    source_name: str = "dim_quiz_questions_enhanced",
) -> str:
    """Return Cypher MERGE query for QuizQuestion nodes."""
    return build_node_merge_query(
        label="QuizQuestion",
        merge_key_field="id",
        write_once_fields=[],
        mutable_fields=[
            "quiz_id",
            "question_id",
            "question_order",
            "points_value",
            "correct_answer",
        ],
    )
