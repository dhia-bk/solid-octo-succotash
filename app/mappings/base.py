"""
Shared typed abstractions and validators for the mapping layer.

This module defines the contract language used by app/mappings/* to declare
how warehouse sources become graph nodes, relationships, and enrichments.

It is the foundation of the mapping layer and provides:

- FieldTransformKind: the allowed field-level transform behaviors
- GraphArtifactKind: the allowed graph artifact categories
- CanonicalizerRequirement: the declaration of when a mapping depends on
  entity canonicalization
- FieldMapping: the atomic rule for mapping one source field to one target
  graph property (or explicitly dropping it)
- EndpointSpec: the typed rule for resolving a graph endpoint identity
- NodeMappingSpec: the full mapping contract for a node-producing source
- RelationshipMappingSpec: the full mapping contract for a relationship-
  producing source
- MappingValidationResult: the structured result of validating a mapping spec

Design rules:
- This module defines the typed language of mapping, not actual per-source
  mappings. No domain-specific mapping registry or transformer logic belongs
  here.
- This module must not import app/mappings/registry.py, any domain mapping
  file, or any transformer module.
- Validators in this file perform structural validation only. They confirm
  that mapping specs are well-formed, internally consistent, and aligned with
  registered graph labels / relationship types / inclusion categories.
- Node and relationship contract names are treated as opaque strings here.
  This module validates that they are non-empty, but does not import graph
  contract classes directly.
- Canonicalizer requirements are validated structurally only. Domain existence
  and resolver availability are checked later by higher-level registry
  validation.

Primary validation guarantees:
- labels must exist in GRAPH_NODE_LABELS
- relationship types must exist in GRAPH_RELATIONSHIP_TYPES
- inclusion modes must exist in SOURCE_INCLUSION_CATEGORIES
- required endpoints must declare an id_source_field
- DROP mappings may not declare target_field and must declare drop_reason
- CONSTANT mappings must declare constant_value
- required fields may not be declared as DROP
- canonicalizer requirements must declare a non-empty domain

This file exists so later mapping files can be built entirely on these
dataclasses and validators, ensuring that malformed mapping specs are caught
before transformers or loaders exist.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from app.core.constants import (
    GRAPH_NODE_LABELS,
    GRAPH_RELATIONSHIP_TYPES,
    SOURCE_INCLUSION_CATEGORIES,
)


# Enums / constant sets


class FieldTransformKind(str, Enum):
    """
    Supported field-level transform behaviors for mapping specs.
    """

    DIRECT = "direct"
    RENAME = "rename"
    DROP = "drop"
    CONSTANT = "constant"
    CANONICAL_ID = "canonical_id"
    SYNTHETIC_ID = "synthetic_id"
    TEMPORAL_NORMALIZE = "temporal_normalize"
    DATE_AS_LABEL = "date_as_label"
    JSON_PARSE = "json_parse"
    LIST_NORMALIZE = "list_normalize"
    CUSTOM = "custom"


class GraphArtifactKind(str, Enum):
    """
    High-level graph artifact categories emitted by mappings.
    """

    NODE = "node"
    RELATIONSHIP = "relationship"
    ENRICHMENT = "enrichment"


# Typed mapping building blocks


@dataclass(frozen=True)
class CanonicalizerRequirement:
    """
    Canonicalization requirement for a field or endpoint.

    Attributes:
        domain: Canonicalizer domain name, e.g. "teams", "tags", "competitions".
        resolver_method: Optional domain-specific resolver method, e.g.
            "resolve_team_id", "resolve_tag_name". When None, callers should use
            the base resolve() path.
        required: Whether unresolved values must fail hard.
    """

    domain: str
    resolver_method: str | None
    required: bool


@dataclass(frozen=True)
class FieldMapping:
    """
    Atomic mapping rule for one source field.

    Attributes:
        source_field: Source field name from warehouse row.
        target_field: Target graph property name. May be None for DROP mappings.
        transform_kind: One of FieldTransformKind values.
        required: Whether the source field must be present/non-null for mapping.
        drop_reason: Required when transform_kind is DROP.
        constant_value: Required when transform_kind is CONSTANT.
        canonicalizer: Canonicalizer requirement when transform_kind depends on
            entity normalization.
        notes: Optional explanatory notes for maintainers and validators.
    """

    source_field: str
    target_field: str | None
    transform_kind: str
    required: bool
    drop_reason: str | None
    constant_value: Any | None
    canonicalizer: CanonicalizerRequirement | None
    notes: str | None


@dataclass(frozen=True)
class EndpointSpec:
    """
    Mapping rule for a graph endpoint.

    Used for relationship endpoints and node identity resolution where a source
    field must be resolved into a graph-stable node identity.

    Attributes:
        endpoint_name: Logical endpoint identifier, usually "start", "end",
            or "node".
        label: Fixed graph label when known statically.
        label_from_field: Source field used when endpoint label is dynamic.
        id_source_field: Source field supplying the raw ID or alias.
        canonicalizer: Canonicalizer requirement if endpoint resolution depends
            on alias normalization.
        merge_key_strategy: Logical merge-key strategy name for this endpoint.
        required: Whether the endpoint must resolve for the mapping to proceed.
        notes: Optional explanatory notes.
    """

    endpoint_name: str
    label: str | None
    label_from_field: str | None
    id_source_field: str | None
    canonicalizer: CanonicalizerRequirement | None
    merge_key_strategy: str
    required: bool
    notes: str | None


@dataclass(frozen=True)
class NodeMappingSpec:
    """
    Full mapping declaration for a node-producing source.

    Attributes:
        source_name: Source table or logical source name.
        target_label: Graph node label.
        graph_contract_name: Target graph contract class name, e.g. "UserNode".
        artifact_kind: GraphArtifactKind.NODE or GraphArtifactKind.ENRICHMENT.
        inclusion_mode: Source inclusion category.
        id_strategy: Logical strategy name for node identity construction.
        id_source_fields: Source fields used to build the graph node ID.
        field_mappings: Property-level mapping rules.
        property_owner_source: Source declared authoritative for written
            properties on this target.
        temporal_mode: Optional temporal behavior marker.
        notes: Optional explanatory notes.
    """

    source_name: str
    target_label: str
    graph_contract_name: str
    artifact_kind: str
    inclusion_mode: str
    id_strategy: str
    id_source_fields: tuple[str, ...]
    field_mappings: tuple[FieldMapping, ...]
    property_owner_source: str
    temporal_mode: str | None
    notes: str | None


@dataclass(frozen=True)
class RelationshipMappingSpec:
    """
    Full mapping declaration for a relationship-producing source.

    Attributes:
        source_name: Source table or logical source name.
        rel_type: Graph relationship type.
        graph_contract_name: Target relationship contract class name, e.g.
            "PredictedRel".
        artifact_kind: GraphArtifactKind.RELATIONSHIP or ENRICHMENT.
        inclusion_mode: Source inclusion category.
        start_endpoint: Start-node resolution rule.
        end_endpoint: End-node resolution rule.
        field_mappings: Relationship property mapping rules.
        relationship_key_strategy: Logical relationship identity / dedupe strategy.
        notes: Optional explanatory notes.
    """

    source_name: str
    rel_type: str
    graph_contract_name: str
    artifact_kind: str
    inclusion_mode: str
    start_endpoint: EndpointSpec
    end_endpoint: EndpointSpec
    field_mappings: tuple[FieldMapping, ...]
    relationship_key_strategy: str
    notes: str | None


@dataclass(frozen=True)
class MappingValidationResult:
    """
    Structured validation result for one source mapping bundle.
    """

    source_name: str
    is_valid: bool
    errors: tuple[str, ...]
    warnings: tuple[str, ...]


# Public validator helpers


def validate_canonicalizer_requirement(
    requirement: CanonicalizerRequirement,
) -> list[str]:
    """
    Validate a CanonicalizerRequirement.

    Returns:
        List of error strings. Empty list means valid.
    """
    errors: list[str] = []

    if not requirement.domain or not requirement.domain.strip():
        errors.append("canonicalizer.domain cannot be empty")

    if requirement.resolver_method is not None and not requirement.resolver_method.strip():
        errors.append("canonicalizer.resolver_method cannot be blank if provided")

    return errors


def validate_endpoint_spec(spec: EndpointSpec) -> list[str]:
    """
    Validate an EndpointSpec.

    Checks:
    - endpoint_name is non-empty
    - at least one of label or label_from_field is provided
    - fixed label is valid if provided
    - required endpoints declare an id_source_field
    - merge_key_strategy is non-empty
    - canonicalizer requirement is valid if present
    """
    errors: list[str] = []

    if not spec.endpoint_name or not spec.endpoint_name.strip():
        errors.append("endpoint_name cannot be empty")

    if spec.label is None and spec.label_from_field is None:
        errors.append(
            f"EndpointSpec[{spec.endpoint_name}]: either label or label_from_field must be provided"
        )

    if spec.label is not None and spec.label not in GRAPH_NODE_LABELS:
        errors.append(
            f"EndpointSpec[{spec.endpoint_name}]: label '{spec.label}' is not registered in GRAPH_NODE_LABELS"
        )

    if spec.label_from_field is not None and not spec.label_from_field.strip():
        errors.append(
            f"EndpointSpec[{spec.endpoint_name}]: label_from_field cannot be blank if provided"
        )

    if spec.required and (spec.id_source_field is None or not spec.id_source_field.strip()):
        errors.append(
            f"EndpointSpec[{spec.endpoint_name}]: required endpoint must declare id_source_field"
        )

    if spec.id_source_field is not None and not spec.id_source_field.strip():
        errors.append(
            f"EndpointSpec[{spec.endpoint_name}]: id_source_field cannot be blank if provided"
        )

    if not spec.merge_key_strategy or not spec.merge_key_strategy.strip():
        errors.append(
            f"EndpointSpec[{spec.endpoint_name}]: merge_key_strategy cannot be empty"
        )

    if spec.canonicalizer is not None:
        errors.extend(
            f"EndpointSpec[{spec.endpoint_name}]: {error}"
            for error in validate_canonicalizer_requirement(spec.canonicalizer)
        )

    return errors


def validate_field_mapping(mapping: FieldMapping) -> list[str]:
    """
    Validate a FieldMapping.

    Checks:
    - source_field is non-empty
    - transform_kind is valid
    - DROP mappings have no target_field and include drop_reason
    - CONSTANT mappings include constant_value
    - required fields are not dropped
    - canonicalizer requirements are well formed
    """
    errors: list[str] = []

    if not mapping.source_field or not mapping.source_field.strip():
        errors.append("source_field cannot be empty")

    valid_transform_kinds = {kind.value for kind in FieldTransformKind}
    if mapping.transform_kind not in valid_transform_kinds:
        errors.append(
            f"transform_kind '{mapping.transform_kind}' is not a valid FieldTransformKind"
        )

    if mapping.transform_kind == FieldTransformKind.DROP.value:
        if mapping.target_field is not None:
            errors.append("DROP mappings must not declare target_field")
        if not mapping.drop_reason or not mapping.drop_reason.strip():
            errors.append("DROP mappings must declare drop_reason")
        if mapping.required:
            errors.append("FieldMapping cannot be both required and dropped")
    else:
        if mapping.target_field is None or not mapping.target_field.strip():
            errors.append(
                "Non-DROP mappings must declare a non-empty target_field"
            )

    if mapping.transform_kind == FieldTransformKind.CONSTANT.value and mapping.constant_value is None:
        errors.append("CONSTANT mappings must declare constant_value")

    if mapping.transform_kind != FieldTransformKind.CONSTANT.value and mapping.constant_value is not None:
        errors.append(
            "constant_value may only be set for CONSTANT mappings"
        )

    if mapping.canonicalizer is not None:
        errors.extend(
            f"FieldMapping[{mapping.source_field}]: {error}"
            for error in validate_canonicalizer_requirement(mapping.canonicalizer)
        )

    return errors


def validate_node_mapping_spec(spec: NodeMappingSpec) -> list[str]:
    """
    Validate a NodeMappingSpec.

    Checks:
    - source_name is non-empty
    - target_label is a valid graph label
    - graph_contract_name is non-empty
    - artifact_kind is NODE or ENRICHMENT
    - inclusion_mode is a recognized source inclusion category
    - id_strategy is non-empty
    - id_source_fields are declared
    - property_owner_source is non-empty
    - all field mappings are valid
    """
    errors: list[str] = []

    if not spec.source_name or not spec.source_name.strip():
        errors.append("source_name cannot be empty")

    if spec.target_label not in GRAPH_NODE_LABELS:
        errors.append(
            f"target_label '{spec.target_label}' is not registered in GRAPH_NODE_LABELS"
        )

    if not spec.graph_contract_name or not spec.graph_contract_name.strip():
        errors.append("graph_contract_name cannot be empty")

    valid_artifact_kinds = {
        GraphArtifactKind.NODE.value,
        GraphArtifactKind.ENRICHMENT.value,
    }
    if spec.artifact_kind not in valid_artifact_kinds:
        errors.append(
            f"artifact_kind '{spec.artifact_kind}' must be one of {sorted(valid_artifact_kinds)}"
        )

    if spec.inclusion_mode not in SOURCE_INCLUSION_CATEGORIES:
        errors.append(
            f"inclusion_mode '{spec.inclusion_mode}' is not in SOURCE_INCLUSION_CATEGORIES"
        )

    if not spec.id_strategy or not spec.id_strategy.strip():
        errors.append("id_strategy cannot be empty")

    if not spec.id_source_fields:
        errors.append("id_source_fields must contain at least one field")

    if any(not field or not field.strip() for field in spec.id_source_fields):
        errors.append("id_source_fields cannot contain empty values")

    if not spec.property_owner_source or not spec.property_owner_source.strip():
        errors.append("property_owner_source cannot be empty")

    if not spec.field_mappings:
        errors.append("field_mappings must contain at least one FieldMapping")

    for idx, field_mapping in enumerate(spec.field_mappings):
        field_errors = validate_field_mapping(field_mapping)
        errors.extend(
            f"field_mappings[{idx}] ({field_mapping.source_field!r}): {error}"
            for error in field_errors
        )

    return errors


def validate_relationship_mapping_spec(
    spec: RelationshipMappingSpec,
) -> list[str]:
    """
    Validate a RelationshipMappingSpec.

    Checks:
    - source_name is non-empty
    - rel_type is a valid graph relationship type
    - graph_contract_name is non-empty
    - artifact_kind is RELATIONSHIP or ENRICHMENT
    - inclusion_mode is a recognized source inclusion category
    - start and end endpoints are valid
    - relationship_key_strategy is non-empty
    - all field mappings are valid
    """
    errors: list[str] = []

    if not spec.source_name or not spec.source_name.strip():
        errors.append("source_name cannot be empty")

    if spec.rel_type not in GRAPH_RELATIONSHIP_TYPES:
        errors.append(
            f"rel_type '{spec.rel_type}' is not registered in GRAPH_RELATIONSHIP_TYPES"
        )

    if not spec.graph_contract_name or not spec.graph_contract_name.strip():
        errors.append("graph_contract_name cannot be empty")

    valid_artifact_kinds = {
        GraphArtifactKind.RELATIONSHIP.value,
        GraphArtifactKind.ENRICHMENT.value,
    }
    if spec.artifact_kind not in valid_artifact_kinds:
        errors.append(
            f"artifact_kind '{spec.artifact_kind}' must be one of {sorted(valid_artifact_kinds)}"
        )

    if spec.inclusion_mode not in SOURCE_INCLUSION_CATEGORIES:
        errors.append(
            f"inclusion_mode '{spec.inclusion_mode}' is not in SOURCE_INCLUSION_CATEGORIES"
        )

    errors.extend(
        f"start_endpoint: {error}"
        for error in validate_endpoint_spec(spec.start_endpoint)
    )
    errors.extend(
        f"end_endpoint: {error}"
        for error in validate_endpoint_spec(spec.end_endpoint)
    )

    if not spec.relationship_key_strategy or not spec.relationship_key_strategy.strip():
        errors.append("relationship_key_strategy cannot be empty")

    for idx, field_mapping in enumerate(spec.field_mappings):
        field_errors = validate_field_mapping(field_mapping)
        errors.extend(
            f"field_mappings[{idx}] ({field_mapping.source_field!r}): {error}"
            for error in field_errors
        )

    return errors