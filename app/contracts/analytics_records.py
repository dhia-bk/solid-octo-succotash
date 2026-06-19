"""
Typed contract layer for analytics layer payloads.

This module defines the records produced by the analytics pipeline and consumed
by the inference, serving, and API layers.

Design rules:
- No analytics layer function may return a raw dict to a downstream layer.
- Every record type is frozen and validated at construction time.
- activity_weight values are validated against [ACTIVITY_WEIGHT_MIN, ACTIVITY_WEIGHT_MAX]
  via assert_activity_weight_valid() from app.schemas.graph.properties.
- confidence_score values are validated against [0.0, 1.0] at the contract boundary.
- InferenceRecord is the typed bridge between the analytics layer and the graph
  loader — inference results are written to the graph via NodeRecord, not directly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.core.constants import GRAPH_NODE_LABELS
from app.core.exceptions import ValidationError
from app.core.time import format_iso_timestamp, utc_now
from app.schemas.graph.properties import assert_activity_weight_valid


# Confidence score bounds


CONFIDENCE_SCORE_MIN: float = 0.0
CONFIDENCE_SCORE_MAX: float = 1.0



# TribeAssignmentRecord



@dataclass(frozen=True)
class TribeAssignmentRecord:
    """
    Typed payload for a single Leiden community assignment.

    Produced by the Leiden analytics job, consumed by the inference layer
    and serving materialization.

    Attributes:
        user_id:           Canonical User node ID.
        tribe_id:          Canonical tribe/community identifier from Leiden output.
        leiden_run_id:     Run ID of the Leiden execution that produced this record.
        algorithm_version: Version marker for the Leiden algorithm configuration.
        assigned_at:       ISO UTC timestamp when the assignment was written.
        modularity_score:  Modularity quality score for the community, if available.
        community_size:    Number of members in the assigned community, if available.
    """

    user_id: str
    tribe_id: str
    leiden_run_id: str
    algorithm_version: str
    assigned_at: str
    modularity_score: float | None
    community_size: int | None

    def __post_init__(self) -> None:
        errors = validate_tribe_assignment_record(self)
        if errors:
            raise ValidationError(
                "TribeAssignmentRecord failed validation",
                errors=errors,
                user_id=self.user_id,
                tribe_id=self.tribe_id,
            )

    def has_quality_metrics(self) -> bool:
        """Return True if modularity score and community size are both present."""
        return self.modularity_score is not None and self.community_size is not None



# PageRankRecord



@dataclass(frozen=True)
class PageRankRecord:
    """
    Typed payload for a single PageRank score.

    Produced by the PageRank analytics job, consumed by the serving layer
    and tribe analysis.

    Attributes:
        node_id:           Canonical graph node ID.
        label:             Graph node label. Must be in GRAPH_NODE_LABELS.
        pagerank_score:    Computed PageRank score. Must be >= 0.0.
        pagerank_run_id:   Run ID of the PageRank execution that produced this record.
        algorithm_version: Version marker for the PageRank algorithm configuration.
        computed_at:       ISO UTC timestamp when the score was computed.
    """

    node_id: str
    label: str
    pagerank_score: float
    pagerank_run_id: str
    algorithm_version: str
    computed_at: str

    def __post_init__(self) -> None:
        errors = validate_pagerank_record(self)
        if errors:
            raise ValidationError(
                "PageRankRecord failed validation",
                errors=errors,
                node_id=self.node_id,
                label=self.label,
            )



# InferenceRecord



@dataclass(frozen=True)
class InferenceRecord:
    """
    Typed payload for a single label inference result.

    Produced by the inference layer, consumed by the serving layer and
    written to the graph via NodeRecord. InferenceRecord is the typed bridge
    between analytics outputs and graph writes — it is never written directly.

    Attributes:
        user_id:           Canonical User node ID the inference applies to.
        inferred_tribe_id: Inferred tribe ID, or None if inference was inconclusive.
        confidence_score:  Confidence in the inference, in [0.0, 1.0], or None.
        inference_run_id:  Run ID of the inference execution.
        model_version:     Version marker for the inference model.
        label_type:        Logical label category (e.g. "tribe_assignment").
        inferred_at:       ISO UTC timestamp when inference was computed.
    """

    user_id: str
    inferred_tribe_id: str | None
    confidence_score: float | None
    inference_run_id: str
    model_version: str
    label_type: str
    inferred_at: str

    def __post_init__(self) -> None:
        errors = validate_inference_record(self)
        if errors:
            raise ValidationError(
                "InferenceRecord failed validation",
                errors=errors,
                user_id=self.user_id,
                label_type=self.label_type,
            )

    def is_conclusive(self) -> bool:
        """Return True if inference produced a tribe assignment."""
        return self.inferred_tribe_id is not None

    def is_high_confidence(self, threshold: float = 0.8) -> bool:
        """
        Return True if the confidence score meets or exceeds the threshold.

        Args:
            threshold: Minimum confidence level. Defaults to 0.8.

        Returns:
            False if confidence_score is None.
        """
        if self.confidence_score is None:
            return False
        return self.confidence_score >= threshold



# PersonaStateRecord



@dataclass(frozen=True)
class PersonaStateRecord:
    """
    Typed payload for a computed persona state snapshot.

    Produced by the temporal/persona analytics pipeline, consumed by the
    serving layer and written to the graph as a PersonaState node.

    Attributes:
        user_id:               Canonical User node ID.
        pcm_stage:             PCM (Process Communication Model) stage label.
        behaviour_label:       Computed behaviour classification, if available.
        birfing_coefficient:   BIRFING coefficient value, if computed.
        frustration_bias:      Frustration bias value, if computed.
        calculated_at:         ISO UTC timestamp when the state was calculated.
        pipeline_run_id:       Run ID of the pipeline execution.
    """

    user_id: str
    pcm_stage: str
    behaviour_label: str | None
    birfing_coefficient: float | None
    frustration_bias: float | None
    calculated_at: str
    pipeline_run_id: str

    def __post_init__(self) -> None:
        errors = validate_persona_state_record(self)
        if errors:
            raise ValidationError(
                "PersonaStateRecord failed validation",
                errors=errors,
                user_id=self.user_id,
                pcm_stage=self.pcm_stage,
            )

    def has_full_persona(self) -> bool:
        """Return True if all optional persona fields are populated."""
        return (
            self.behaviour_label is not None
            and self.birfing_coefficient is not None
            and self.frustration_bias is not None
        )



# ActivityWeightRecord



@dataclass(frozen=True)
class ActivityWeightRecord:
    """
    Typed payload for a computed activity weight on a membership edge.

    Produced by the weighting pipeline, consumed by the GDS projection layer.
    The activity_weight is written as a property on MEMBER_OF edges and used
    as the edge weight for Leiden community detection and PageRank.

    Attributes:
        user_id:            Canonical User node ID.
        private_league_id:  Canonical PrivateLeague node ID.
        activity_weight:    Computed weight. Must be in [0.0, 1.0].
        weighting_version:  Version marker for the weighting formula.
        computed_at:        ISO UTC timestamp when the weight was computed.
    """

    user_id: str
    private_league_id: str
    activity_weight: float
    weighting_version: str
    computed_at: str

    def __post_init__(self) -> None:
        errors = validate_activity_weight_record(self)
        if errors:
            raise ValidationError(
                "ActivityWeightRecord failed validation",
                errors=errors,
                user_id=self.user_id,
                private_league_id=self.private_league_id,
                activity_weight=self.activity_weight,
            )

    def is_above_threshold(self, threshold: float = 0.0) -> bool:
        """
        Return True if activity_weight exceeds the given threshold.

        Used by GDS membership filters to exclude low-weight edges.

        Args:
            threshold: Minimum weight (exclusive). Defaults to 0.0.
        """
        return self.activity_weight > threshold



# Validation helpers (public)



def validate_tribe_assignment_record(record: TribeAssignmentRecord) -> list[str]:
    """
    Validate a TribeAssignmentRecord and return a list of error strings.

    Checks:
    - user_id is non-empty
    - tribe_id is non-empty
    - leiden_run_id is non-empty
    - algorithm_version is non-empty
    - assigned_at is non-empty
    - modularity_score is in [0.0, 1.0] if not None
    - community_size is >= 1 if not None

    Args:
        record: TribeAssignmentRecord to validate.

    Returns:
        List of error strings. Empty list means the record is valid.
    """
    errors: list[str] = []

    if not record.user_id or not record.user_id.strip():
        errors.append("user_id cannot be empty")

    if not record.tribe_id or not record.tribe_id.strip():
        errors.append("tribe_id cannot be empty")

    if not record.leiden_run_id or not record.leiden_run_id.strip():
        errors.append("leiden_run_id cannot be empty")

    if not record.algorithm_version or not record.algorithm_version.strip():
        errors.append("algorithm_version cannot be empty")

    if not record.assigned_at or not record.assigned_at.strip():
        errors.append("assigned_at cannot be empty")

    if record.modularity_score is not None and not (0.0 <= record.modularity_score <= 1.0):
        errors.append(
            f"modularity_score must be in [0.0, 1.0], got {record.modularity_score}"
        )

    if record.community_size is not None and record.community_size < 1:
        errors.append(
            f"community_size must be >= 1 if present, got {record.community_size}"
        )

    return errors


def validate_pagerank_record(record: PageRankRecord) -> list[str]:
    """
    Validate a PageRankRecord and return a list of error strings.

    Checks:
    - node_id is non-empty
    - label is registered in GRAPH_NODE_LABELS
    - pagerank_score is >= 0.0
    - pagerank_run_id is non-empty
    - algorithm_version is non-empty
    - computed_at is non-empty

    Args:
        record: PageRankRecord to validate.

    Returns:
        List of error strings. Empty list means the record is valid.
    """
    errors: list[str] = []

    if not record.node_id or not record.node_id.strip():
        errors.append("node_id cannot be empty")

    if record.label not in GRAPH_NODE_LABELS:
        errors.append(
            f"label '{record.label}' is not registered in GRAPH_NODE_LABELS"
        )

    if record.pagerank_score < 0.0:
        errors.append(
            f"pagerank_score must be >= 0.0, got {record.pagerank_score}"
        )

    if not record.pagerank_run_id or not record.pagerank_run_id.strip():
        errors.append("pagerank_run_id cannot be empty")

    if not record.algorithm_version or not record.algorithm_version.strip():
        errors.append("algorithm_version cannot be empty")

    if not record.computed_at or not record.computed_at.strip():
        errors.append("computed_at cannot be empty")

    return errors


def validate_inference_record(record: InferenceRecord) -> list[str]:
    """
    Validate an InferenceRecord and return a list of error strings.

    Checks:
    - user_id is non-empty
    - inference_run_id is non-empty
    - model_version is non-empty
    - label_type is non-empty
    - inferred_at is non-empty
    - confidence_score is in [0.0, 1.0] if not None

    Args:
        record: InferenceRecord to validate.

    Returns:
        List of error strings. Empty list means the record is valid.
    """
    errors: list[str] = []

    if not record.user_id or not record.user_id.strip():
        errors.append("user_id cannot be empty")

    if not record.inference_run_id or not record.inference_run_id.strip():
        errors.append("inference_run_id cannot be empty")

    if not record.model_version or not record.model_version.strip():
        errors.append("model_version cannot be empty")

    if not record.label_type or not record.label_type.strip():
        errors.append("label_type cannot be empty")

    if not record.inferred_at or not record.inferred_at.strip():
        errors.append("inferred_at cannot be empty")

    if record.confidence_score is not None and not (
        CONFIDENCE_SCORE_MIN <= record.confidence_score <= CONFIDENCE_SCORE_MAX
    ):
        errors.append(
            f"confidence_score must be in [{CONFIDENCE_SCORE_MIN}, {CONFIDENCE_SCORE_MAX}]"
            f" if not None, got {record.confidence_score}"
        )

    return errors


def validate_persona_state_record(record: PersonaStateRecord) -> list[str]:
    """
    Validate a PersonaStateRecord and return a list of error strings.

    Checks:
    - user_id is non-empty
    - pcm_stage is non-empty
    - calculated_at is non-empty
    - pipeline_run_id is non-empty

    Args:
        record: PersonaStateRecord to validate.

    Returns:
        List of error strings. Empty list means the record is valid.
    """
    errors: list[str] = []

    if not record.user_id or not record.user_id.strip():
        errors.append("user_id cannot be empty")

    if not record.pcm_stage or not record.pcm_stage.strip():
        errors.append("pcm_stage cannot be empty")

    if not record.calculated_at or not record.calculated_at.strip():
        errors.append("calculated_at cannot be empty")

    if not record.pipeline_run_id or not record.pipeline_run_id.strip():
        errors.append("pipeline_run_id cannot be empty")

    return errors


def validate_activity_weight_record(record: ActivityWeightRecord) -> list[str]:
    """
    Validate an ActivityWeightRecord and return a list of error strings.

    Checks:
    - user_id is non-empty
    - private_league_id is non-empty
    - weighting_version is non-empty
    - computed_at is non-empty
    - activity_weight is in [ACTIVITY_WEIGHT_MIN, ACTIVITY_WEIGHT_MAX]
      via assert_activity_weight_valid() from app.schemas.graph.properties

    Args:
        record: ActivityWeightRecord to validate.

    Returns:
        List of error strings. Empty list means the record is valid.
    """
    errors: list[str] = []

    if not record.user_id or not record.user_id.strip():
        errors.append("user_id cannot be empty")

    if not record.private_league_id or not record.private_league_id.strip():
        errors.append("private_league_id cannot be empty")

    if not record.weighting_version or not record.weighting_version.strip():
        errors.append("weighting_version cannot be empty")

    if not record.computed_at or not record.computed_at.strip():
        errors.append("computed_at cannot be empty")

    # Delegate range check to the canonical validator in properties.py.
    # SchemaMappingError is caught and surfaced as a validation error string.
    try:
        assert_activity_weight_valid(record.activity_weight)
    except Exception as exc:  # noqa: BLE001
        errors.append(f"activity_weight validation failed: {exc}")

    return errors



# Factory helpers



def build_tribe_assignment_record(
    *,
    user_id: str,
    tribe_id: str,
    leiden_run_id: str,
    algorithm_version: str,
    modularity_score: float | None = None,
    community_size: int | None = None,
    assigned_at: str | None = None,
) -> TribeAssignmentRecord:
    """
    Construct a validated TribeAssignmentRecord.

    Args:
        user_id:           Canonical User node ID.
        tribe_id:          Leiden-assigned tribe/community ID.
        leiden_run_id:     Run ID of the Leiden execution.
        algorithm_version: Version marker for the algorithm configuration.
        modularity_score:  Optional community modularity quality score.
        community_size:    Optional community member count.
        assigned_at:       Optional ISO timestamp. Defaults to utc_now().

    Returns:
        Validated TribeAssignmentRecord.

    Raises:
        ValidationError: If the record fails any validation check.
    """
    return TribeAssignmentRecord(
        user_id=user_id,
        tribe_id=tribe_id,
        leiden_run_id=leiden_run_id,
        algorithm_version=algorithm_version,
        assigned_at=assigned_at or format_iso_timestamp(utc_now()),
        modularity_score=modularity_score,
        community_size=community_size,
    )


def build_pagerank_record(
    *,
    node_id: str,
    label: str,
    pagerank_score: float,
    pagerank_run_id: str,
    algorithm_version: str,
    computed_at: str | None = None,
) -> PageRankRecord:
    """
    Construct a validated PageRankRecord.

    Args:
        node_id:           Canonical graph node ID.
        label:             Graph node label. Must be in GRAPH_NODE_LABELS.
        pagerank_score:    Computed PageRank score. Must be >= 0.0.
        pagerank_run_id:   Run ID of the PageRank execution.
        algorithm_version: Version marker for the algorithm configuration.
        computed_at:       Optional ISO timestamp. Defaults to utc_now().

    Returns:
        Validated PageRankRecord.

    Raises:
        ValidationError: If the record fails any validation check.
    """
    return PageRankRecord(
        node_id=node_id,
        label=label,
        pagerank_score=pagerank_score,
        pagerank_run_id=pagerank_run_id,
        algorithm_version=algorithm_version,
        computed_at=computed_at or format_iso_timestamp(utc_now()),
    )


def build_inference_record(
    *,
    user_id: str,
    inference_run_id: str,
    model_version: str,
    label_type: str,
    inferred_tribe_id: str | None = None,
    confidence_score: float | None = None,
    inferred_at: str | None = None,
) -> InferenceRecord:
    """
    Construct a validated InferenceRecord.

    Args:
        user_id:           Canonical User node ID.
        inference_run_id:  Run ID of the inference execution.
        model_version:     Version marker for the inference model.
        label_type:        Logical label category (e.g. "tribe_assignment").
        inferred_tribe_id: Inferred tribe ID, or None if inconclusive.
        confidence_score:  Confidence in [0.0, 1.0], or None.
        inferred_at:       Optional ISO timestamp. Defaults to utc_now().

    Returns:
        Validated InferenceRecord.

    Raises:
        ValidationError: If the record fails any validation check.
    """
    return InferenceRecord(
        user_id=user_id,
        inferred_tribe_id=inferred_tribe_id,
        confidence_score=confidence_score,
        inference_run_id=inference_run_id,
        model_version=model_version,
        label_type=label_type,
        inferred_at=inferred_at or format_iso_timestamp(utc_now()),
    )


def build_persona_state_record(
    *,
    user_id: str,
    pcm_stage: str,
    pipeline_run_id: str,
    behaviour_label: str | None = None,
    birfing_coefficient: float | None = None,
    frustration_bias: float | None = None,
    calculated_at: str | None = None,
) -> PersonaStateRecord:
    """
    Construct a validated PersonaStateRecord.

    Args:
        user_id:               Canonical User node ID.
        pcm_stage:             PCM stage label.
        pipeline_run_id:       Run ID of the pipeline execution.
        behaviour_label:       Optional behaviour classification.
        birfing_coefficient:   Optional BIRFING coefficient.
        frustration_bias:      Optional frustration bias value.
        calculated_at:         Optional ISO timestamp. Defaults to utc_now().

    Returns:
        Validated PersonaStateRecord.

    Raises:
        ValidationError: If the record fails any validation check.
    """
    return PersonaStateRecord(
        user_id=user_id,
        pcm_stage=pcm_stage,
        behaviour_label=behaviour_label,
        birfing_coefficient=birfing_coefficient,
        frustration_bias=frustration_bias,
        calculated_at=calculated_at or format_iso_timestamp(utc_now()),
        pipeline_run_id=pipeline_run_id,
    )


def build_activity_weight_record(
    *,
    user_id: str,
    private_league_id: str,
    activity_weight: float,
    weighting_version: str,
    computed_at: str | None = None,
) -> ActivityWeightRecord:
    """
    Construct a validated ActivityWeightRecord.

    Args:
        user_id:            Canonical User node ID.
        private_league_id:  Canonical PrivateLeague node ID.
        activity_weight:    Computed weight. Must be in [0.0, 1.0].
        weighting_version:  Version marker for the weighting formula.
        computed_at:        Optional ISO timestamp. Defaults to utc_now().

    Returns:
        Validated ActivityWeightRecord.

    Raises:
        ValidationError: If the record fails any validation check.
    """
    return ActivityWeightRecord(
        user_id=user_id,
        private_league_id=private_league_id,
        activity_weight=activity_weight,
        weighting_version=weighting_version,
        computed_at=computed_at or format_iso_timestamp(utc_now()),
    )