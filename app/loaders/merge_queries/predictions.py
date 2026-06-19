"""
Merge queries for predictions.
Source(s): fct_predictions
"""

from __future__ import annotations

from app.loaders.merge_queries.base import build_relationship_merge_query

PREDICTIONS_BATCH_SIZE: int = 500  # Override default for high-volume source


def get_predicted_merge_query(source_name: str = "fct_predictions") -> str:
    """Return Cypher MERGE query for PREDICTED (User→Match) from source_name."""
    return build_relationship_merge_query(
        rel_type="PREDICTED",
        start_label="User",
        end_label="Match",
        start_merge_field="id",
        end_merge_field="id",
        rel_merge_fields=["prediction_id"],
        rel_property_fields=[
            "predicted_at",
            "predicted_outcome",
            "points_awarded",
            "is_correct_result",
            "activity_weight",
            "prediction_type",
        ],
    )
