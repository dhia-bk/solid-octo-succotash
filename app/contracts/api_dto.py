"""
API-facing data transfer objects for Project Pulse Knowledge Graph.

This module defines the output shapes produced by the service and route layers.
DTOs are the final serialization boundary — everything that reaches a caller
must pass through one of these types.

Design rules:
- DTOs must never contain warehouse-layer types, graph node types, or analytics
  records. They are the public contract, not an internal one.
- No pipeline_run_id, leiden_run_id, batch_id, or any internal run identifier
  belongs in a DTO. These are meaningless to API callers.
- No PII fields: no email, password, auth tokens, raw birthdate, or national IDs.
- All DTO fields must be JSON-serializable primitives (str, int, float, bool,
  None, list, dict). No datetime objects, no custom types.
- dto_to_dict() is the only permitted serialization path. Route handlers must
  not call dataclasses.asdict() directly.
"""

from __future__ import annotations

import dataclasses
from typing import Any

from app.core.exceptions import ValidationError
from app.core.time import format_iso_timestamp, utc_now


# PII field audit registry

# Fields that must never appear on any DTO. If a service layer accidentally
# maps a PII field onto a DTO, _assert_dto_no_pii() will catch it at
# construction time.

_DTO_FORBIDDEN_FIELDS: frozenset[str] = frozenset(
    {
        "email",
        "email_address",
        "user_email",
        "password",
        "password_hash",
        "hashed_password",
        "raw_password",
        "auth_token",
        "access_token",
        "refresh_token",
        "api_key",
        "session_token",
        "device_token",
        "push_token",
        "fcm_token",
        "birthdate",
        "birth_date",
        "date_of_birth",
        "dob",
        "raw_birthdate",
        "phone",
        "phone_number",
        "mobile",
        "national_id",
        "passport_number",
        "pipeline_run_id",
        "leiden_run_id",
        "pagerank_run_id",
        "inference_run_id",
        "batch_id",
    }
)


def _assert_dto_no_pii(dto_class_name: str, field_names: list[str]) -> None:
    """
    Assert that a DTO's field names contain no forbidden PII or internal fields.

    Called once at class definition time via the dataclass __post_init__.
    Because DTOs are frozen dataclasses, their field names are fixed — this
    check is structural, not per-instance.

    Args:
        dto_class_name: Name of the DTO class for error messages.
        field_names:    List of field names declared on the DTO.

    Raises:
        ValidationError: If any forbidden field is declared on the DTO.
    """
    violations = sorted(f for f in field_names if f in _DTO_FORBIDDEN_FIELDS)
    if violations:
        raise ValidationError(
            "DTO declares forbidden PII or internal fields",
            dto_class=dto_class_name,
            forbidden_fields=violations,
        )



# UserProfileDTO



@dataclasses.dataclass(frozen=True)
class UserProfileDTO:
    """
    Public profile summary for a single user.

    Consumed by GET /users/{user_id} and user-facing feature endpoints.

    Deliberately excludes: email, password, birthdate, auth tokens, raw
    device identifiers, and any internal pipeline run IDs.

    Attributes:
        user_id:                    Canonical user identifier.
        user_name:                  Display name, if available.
        country:                    ISO country code, if available.
        gender:                     Gender label, if available.
        age:                        Derived age in years, if available.
        current_subscription_name:  Active subscription product name, if any.
        duel_rating:                Current duel rating score, if available.
        tribe_id:                   Assigned tribe identifier, if available.
        current_pcm_stage:          Current PCM stage label, if available.
        behaviour_label:            Computed behaviour label, if available.
        ai_remaining_credits:       Remaining AI interaction credits, if available.
    """

    user_id: str
    user_name: str | None
    country: str | None
    gender: str | None
    age: int | None
    current_subscription_name: str | None
    duel_rating: float | None
    tribe_id: str | None
    current_pcm_stage: str | None
    behaviour_label: str | None
    ai_remaining_credits: int | None

    def __post_init__(self) -> None:
        if not self.user_id or not self.user_id.strip():
            raise ValidationError(
                "UserProfileDTO.user_id cannot be empty",
                field="user_id",
            )

    def has_tribe(self) -> bool:
        """Return True if a tribe assignment is present."""
        return self.tribe_id is not None

    def has_persona(self) -> bool:
        """Return True if a PCM stage is present."""
        return self.current_pcm_stage is not None



# TribeSummaryDTO



@dataclasses.dataclass(frozen=True)
class TribeSummaryDTO:
    """
    Aggregate summary for a single tribe/community.

    Consumed by GET /tribes/{tribe_id} and tribe analytics endpoints.

    Attributes:
        tribe_id:           Canonical tribe identifier.
        member_count:       Number of members assigned to this tribe.
        top_teams:          Ordered list of most-favoured team canonical IDs.
        top_topics:         Ordered list of most-engaged topic canonical labels.
        avg_pagerank:       Mean PageRank score across tribe members, if computed.
        avg_duel_rating:    Mean duel rating across tribe members, if available.
        dominant_pcm_stage: Most common PCM stage in the tribe, if computed.
        cohesion_score:     Graph-level cohesion/modularity score, if available.
    """

    tribe_id: str
    member_count: int
    top_teams: list[str]
    top_topics: list[str]
    avg_pagerank: float | None
    avg_duel_rating: float | None
    dominant_pcm_stage: str | None
    cohesion_score: float | None

    def __post_init__(self) -> None:
        if not self.tribe_id or not self.tribe_id.strip():
            raise ValidationError(
                "TribeSummaryDTO.tribe_id cannot be empty",
                field="tribe_id",
            )
        if self.member_count < 0:
            raise ValidationError(
                "TribeSummaryDTO.member_count cannot be negative",
                field="member_count",
                value=self.member_count,
            )

    def is_large(self, threshold: int = 100) -> bool:
        """Return True if the tribe has at least `threshold` members."""
        return self.member_count >= threshold



# PersonaDTO



@dataclasses.dataclass(frozen=True)
class PersonaDTO:
    """
    Persona state summary for a single user.

    Consumed by GET /personas/{user_id} and notification targeting endpoints.

    Attributes:
        user_id:         Canonical user identifier.
        pcm_stage:       Current PCM stage label, if computed.
        behaviour_label: Computed behaviour classification, if available.
        calculated_at:   ISO UTC timestamp of the most recent persona calculation.
    """

    user_id: str
    pcm_stage: str | None
    behaviour_label: str | None
    calculated_at: str | None

    def __post_init__(self) -> None:
        if not self.user_id or not self.user_id.strip():
            raise ValidationError(
                "PersonaDTO.user_id cannot be empty",
                field="user_id",
            )

    def is_computed(self) -> bool:
        """Return True if a PCM stage has been computed for this user."""
        return self.pcm_stage is not None



# InferenceResultDTO



@dataclasses.dataclass(frozen=True)
class InferenceResultDTO:
    """
    Inference result for a single user.

    Consumed by GET /inferences/{user_id} and downstream ML endpoints.

    Attributes:
        user_id:            Canonical user identifier.
        inferred_tribe_id:  Inferred tribe ID, or None if inconclusive.
        confidence_score:   Confidence in [0.0, 1.0], or None.
        model_version:      Version of the inference model used.
        inferred_at:        ISO UTC timestamp of the inference.
        label_type:         Logical label category (e.g. "tribe_assignment").
    """

    user_id: str
    inferred_tribe_id: str | None
    confidence_score: float | None
    model_version: str
    inferred_at: str
    label_type: str

    def __post_init__(self) -> None:
        if not self.user_id or not self.user_id.strip():
            raise ValidationError(
                "InferenceResultDTO.user_id cannot be empty",
                field="user_id",
            )
        if not self.model_version or not self.model_version.strip():
            raise ValidationError(
                "InferenceResultDTO.model_version cannot be empty",
                field="model_version",
            )
        if not self.inferred_at or not self.inferred_at.strip():
            raise ValidationError(
                "InferenceResultDTO.inferred_at cannot be empty",
                field="inferred_at",
            )
        if not self.label_type or not self.label_type.strip():
            raise ValidationError(
                "InferenceResultDTO.label_type cannot be empty",
                field="label_type",
            )
        if self.confidence_score is not None and not (0.0 <= self.confidence_score <= 1.0):
            raise ValidationError(
                "InferenceResultDTO.confidence_score must be in [0.0, 1.0] if not None",
                field="confidence_score",
                value=self.confidence_score,
            )

    def is_conclusive(self) -> bool:
        """Return True if an inferred tribe is present."""
        return self.inferred_tribe_id is not None

    def is_high_confidence(self, threshold: float = 0.8) -> bool:
        """
        Return True if confidence meets or exceeds threshold.

        Args:
            threshold: Minimum confidence level. Defaults to 0.8.

        Returns:
            False if confidence_score is None.
        """
        if self.confidence_score is None:
            return False
        return self.confidence_score >= threshold



# HealthDTO



@dataclasses.dataclass(frozen=True)
class HealthDTO:
    """
    System health check response.

    Consumed by GET /health and infrastructure monitoring.

    Attributes:
        status:               Aggregate health status.
                              One of: "healthy", "degraded", "unhealthy".
        mysql_healthy:        Whether the warehouse connection is healthy.
        neo4j_healthy:        Whether the graph DB connection is healthy.
        metadata_db_healthy:  Whether the metadata DB connection is healthy.
        checked_at:           ISO UTC timestamp of the health check.
        version:              Application version string.
    """

    status: str
    mysql_healthy: bool
    neo4j_healthy: bool
    metadata_db_healthy: bool
    checked_at: str
    version: str

    _VALID_STATUSES: frozenset[str] = dataclasses.field(
        default=frozenset({"healthy", "degraded", "unhealthy"}),
        init=False,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        valid = {"healthy", "degraded", "unhealthy"}
        if self.status not in valid:
            raise ValidationError(
                "HealthDTO.status must be one of: healthy, degraded, unhealthy",
                field="status",
                value=self.status,
            )
        if not self.checked_at or not self.checked_at.strip():
            raise ValidationError(
                "HealthDTO.checked_at cannot be empty",
                field="checked_at",
            )
        if not self.version or not self.version.strip():
            raise ValidationError(
                "HealthDTO.version cannot be empty",
                field="version",
            )

    def is_healthy(self) -> bool:
        """Return True if all systems are fully healthy."""
        return self.status == "healthy"

    def all_dependencies_healthy(self) -> bool:
        """Return True if all individual dependency checks passed."""
        return self.mysql_healthy and self.neo4j_healthy and self.metadata_db_healthy



# PaginatedResponseDTO



@dataclasses.dataclass(frozen=True)
class PaginatedResponseDTO:
    """
    Generic paginated response wrapper.

    Used by all list endpoints to provide consistent pagination metadata.

    Attributes:
        items:      Page of result items. Items must be JSON-serializable.
        total:      Total count of matching items across all pages.
        page:       Current page number (1-indexed).
        page_size:  Maximum items per page.
        has_next:   True if a subsequent page exists.
    """

    items: list[Any]
    total: int
    page: int
    page_size: int
    has_next: bool

    def __post_init__(self) -> None:
        if self.total < 0:
            raise ValidationError(
                "PaginatedResponseDTO.total cannot be negative",
                field="total",
                value=self.total,
            )
        if self.page < 1:
            raise ValidationError(
                "PaginatedResponseDTO.page must be >= 1",
                field="page",
                value=self.page,
            )
        if self.page_size < 1:
            raise ValidationError(
                "PaginatedResponseDTO.page_size must be >= 1",
                field="page_size",
                value=self.page_size,
            )

    def is_empty(self) -> bool:
        """Return True if no items are present on this page."""
        return len(self.items) == 0

    def item_count(self) -> int:
        """Return the number of items on this page."""
        return len(self.items)



# Serialization helpers



def dto_to_dict(dto: Any, *, drop_none: bool = True) -> dict[str, Any]:
    """
    Convert a frozen DTO dataclass to a JSON-safe dict.

    None values are dropped by default so API responses remain compact.
    Use dto_to_dict_keep_nulls() when null fields must be explicitly present
    in the response body.

    Nested dataclasses are recursively converted. Lists and dicts are walked
    to convert any nested dataclass instances they contain.

    Args:
        dto:       A frozen dataclass instance (any DTO type).
        drop_none: If True, keys with None values are excluded from the output.
                   Defaults to True.

    Returns:
        JSON-safe dict representation of the DTO.

    Raises:
        ValidationError: If dto is not a dataclass instance.
    """
    if not dataclasses.is_dataclass(dto) or isinstance(dto, type):
        raise ValidationError(
            "dto_to_dict requires a dataclass instance, not a class or non-dataclass object",
            received_type=type(dto).__name__,
        )

    result: dict[str, Any] = {}

    for f in dataclasses.fields(dto):
        # Skip internal class-level fields (init=False) such as _VALID_STATUSES.
        if not f.init:
            continue

        value = getattr(dto, f.name)

        if drop_none and value is None:
            continue

        result[f.name] = _serialize_value(value, drop_none=drop_none)

    return result


def dto_to_dict_keep_nulls(dto: Any) -> dict[str, Any]:
    """
    Convert a frozen DTO dataclass to a JSON-safe dict, preserving None as null.

    Use this variant when API consumers require explicit null fields in the
    response body (e.g. JSON:API or OpenAPI nullable schemas).

    Args:
        dto: A frozen dataclass instance (any DTO type).

    Returns:
        JSON-safe dict with None values preserved.
    """
    return dto_to_dict(dto, drop_none=False)


def _serialize_value(value: Any, *, drop_none: bool) -> Any:
    """
    Recursively serialize a value to a JSON-safe form.

    Handles:
    - Nested dataclass instances (converted via dto_to_dict)
    - Lists (each item serialized)
    - Dicts (each value serialized, keys preserved)
    - Primitives (str, int, float, bool, None) — returned as-is

    Args:
        value:     Value to serialize.
        drop_none: Whether to drop None values in nested dicts.

    Returns:
        JSON-safe representation.
    """
    if value is None:
        return None

    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return dto_to_dict(value, drop_none=drop_none)

    if isinstance(value, list):
        serialized = [_serialize_value(item, drop_none=drop_none) for item in value]
        if drop_none:
            return [item for item in serialized if item is not None]
        return serialized

    if isinstance(value, dict):
        if drop_none:
            return {
                k: _serialize_value(v, drop_none=drop_none)
                for k, v in value.items()
                if v is not None
            }
        return {k: _serialize_value(v, drop_none=drop_none) for k, v in value.items()}

    # Primitives: str, int, float, bool are returned as-is.
    return value



# Factory helpers



def build_user_profile_dto(
    *,
    user_id: str,
    user_name: str | None = None,
    country: str | None = None,
    gender: str | None = None,
    age: int | None = None,
    current_subscription_name: str | None = None,
    duel_rating: float | None = None,
    tribe_id: str | None = None,
    current_pcm_stage: str | None = None,
    behaviour_label: str | None = None,
    ai_remaining_credits: int | None = None,
) -> UserProfileDTO:
    """
    Construct a UserProfileDTO.

    All optional fields default to None when not available from the graph.
    """
    return UserProfileDTO(
        user_id=user_id,
        user_name=user_name,
        country=country,
        gender=gender,
        age=age,
        current_subscription_name=current_subscription_name,
        duel_rating=duel_rating,
        tribe_id=tribe_id,
        current_pcm_stage=current_pcm_stage,
        behaviour_label=behaviour_label,
        ai_remaining_credits=ai_remaining_credits,
    )


def build_tribe_summary_dto(
    *,
    tribe_id: str,
    member_count: int,
    top_teams: list[str] | None = None,
    top_topics: list[str] | None = None,
    avg_pagerank: float | None = None,
    avg_duel_rating: float | None = None,
    dominant_pcm_stage: str | None = None,
    cohesion_score: float | None = None,
) -> TribeSummaryDTO:
    """
    Construct a TribeSummaryDTO.

    top_teams and top_topics default to empty lists when not provided.
    """
    return TribeSummaryDTO(
        tribe_id=tribe_id,
        member_count=member_count,
        top_teams=top_teams or [],
        top_topics=top_topics or [],
        avg_pagerank=avg_pagerank,
        avg_duel_rating=avg_duel_rating,
        dominant_pcm_stage=dominant_pcm_stage,
        cohesion_score=cohesion_score,
    )


def build_persona_dto(
    *,
    user_id: str,
    pcm_stage: str | None = None,
    behaviour_label: str | None = None,
    calculated_at: str | None = None,
) -> PersonaDTO:
    """Construct a PersonaDTO."""
    return PersonaDTO(
        user_id=user_id,
        pcm_stage=pcm_stage,
        behaviour_label=behaviour_label,
        calculated_at=calculated_at,
    )


def build_inference_result_dto(
    *,
    user_id: str,
    model_version: str,
    label_type: str,
    inferred_tribe_id: str | None = None,
    confidence_score: float | None = None,
    inferred_at: str | None = None,
) -> InferenceResultDTO:
    """
    Construct an InferenceResultDTO.

    inferred_at defaults to utc_now() if not provided.
    """
    return InferenceResultDTO(
        user_id=user_id,
        inferred_tribe_id=inferred_tribe_id,
        confidence_score=confidence_score,
        model_version=model_version,
        inferred_at=inferred_at or format_iso_timestamp(utc_now()),
        label_type=label_type,
    )


def build_health_dto(
    *,
    mysql_healthy: bool,
    neo4j_healthy: bool,
    metadata_db_healthy: bool,
    version: str,
    checked_at: str | None = None,
) -> HealthDTO:
    """
    Construct a HealthDTO, deriving aggregate status from individual checks.

    Status rules:
    - all healthy  → "healthy"
    - any unhealthy → "unhealthy"
    - partial       → "degraded"
    """
    all_healthy = mysql_healthy and neo4j_healthy and metadata_db_healthy
    any_unhealthy = not mysql_healthy or not neo4j_healthy or not metadata_db_healthy

    if all_healthy:
        status = "healthy"
    elif all_healthy is False and any_unhealthy:
        # At least one is down — check if all are down
        all_down = not mysql_healthy and not neo4j_healthy and not metadata_db_healthy
        status = "unhealthy" if all_down else "degraded"
    else:
        status = "degraded"

    return HealthDTO(
        status=status,
        mysql_healthy=mysql_healthy,
        neo4j_healthy=neo4j_healthy,
        metadata_db_healthy=metadata_db_healthy,
        checked_at=checked_at or format_iso_timestamp(utc_now()),
        version=version,
    )


def build_paginated_response(
    *,
    items: list[Any],
    total: int,
    page: int,
    page_size: int,
) -> PaginatedResponseDTO:
    """
    Construct a PaginatedResponseDTO, deriving has_next automatically.

    Args:
        items:      Page of result items.
        total:      Total count across all pages.
        page:       Current page number (1-indexed).
        page_size:  Items per page.

    Returns:
        PaginatedResponseDTO with has_next derived from total and page position.
    """
    has_next = (page * page_size) < total

    return PaginatedResponseDTO(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        has_next=has_next,
    )