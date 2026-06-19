"""
Property-level standards for Project Pulse Knowledge Graph.

This file is the reference for:
- reserved property name constants used across all nodes and relationships
- PII field names that must never appear on graph nodes
- write-once properties that are set at creation and never overwritten
- the canonical activity weight property and its expected value range
- validation helpers for transformer and loader use

Design rules:
- No graph query logic belongs here.
- No node or relationship dataclasses belong here (those are in nodes.py
  and relationships.py).
- This file is the single place to update when property naming conventions
  change or new PII fields are identified.
"""

from __future__ import annotations

from typing import Any

from app.core.exceptions import SchemaMappingError

# ============================================================================
# Reserved cross-node property names
# ============================================================================
# These are written to every node (or specific node groups) by the loader
# layer. No transformer should invent these field names independently.

PROP_ID: str = "id"
PROP_CREATED_AT: str = "created_at"
PROP_UPDATED_AT: str = "updated_at"
PROP_PIPELINE_RUN_ID: str = "pipeline_run_id"
PROP_WEIGHTING_VERSION: str = "weighting_version"
PROP_LOADED_AT: str = "loaded_at"

# ============================================================================
# GDS projection weight property
# ============================================================================
# The canonical property name for the shared-league membership edge weight
# used in GDS graph projections for Leiden community detection and PageRank.
# The weight must always be in [ACTIVITY_WEIGHT_MIN, ACTIVITY_WEIGHT_MAX].

ACTIVITY_WEIGHT_PROPERTY: str = "activity_weight"
ACTIVITY_WEIGHT_MIN: float = 0.0
ACTIVITY_WEIGHT_MAX: float = 1.0

# ============================================================================
# PII property registry
# ============================================================================
# Property names that must NEVER be stored on graph nodes or relationship
# properties. The transformer layer must drop or hash these fields before
# producing any graph record.
#
# If a new PII field is identified, add it here. The assert_no_pii() helper
# will then catch any transformer that accidentally propagates it.

PII_PROPERTY_NAMES: frozenset[str] = frozenset(
    {
        "password",
        "email",
        "user_email",
        "phone",
        "date_of_birth",
        "raw_birthdate",
        "access_token",
        "refresh_token",
        "api_key",
        "auth_token",
        "session_token",
        "private_key",
        "secret",
    }
)

# ============================================================================
# Write-once properties
# ============================================================================
# Properties that are set when a node is first created (via MERGE ON CREATE)
# and must never be overwritten by subsequent pipeline runs or updates.
#
# The loader must use ON CREATE SET for these, not ON MATCH SET.

WRITE_ONCE_PROPERTIES: frozenset[str] = frozenset(
    {
        "id",
        "created_at",
        "user_created_at",
        "earned_at",
        "predicted_at",
        "joined_at",
        "published_at",
        "conversation_start",
        "first_message_at",
        "first_seen_at",
    }
)

# ============================================================================
# Validation helpers
# ============================================================================


def assert_no_pii(properties: dict[str, Any]) -> None:
    """
    Assert that none of the property keys are PII field names.

    This must be called by every transformer before producing a graph record
    and by every loader before writing a merge query.

    Args:
        properties: Dict of property names to values (e.g. a node dataclass
            converted to dict, or a relationship property dict).

    Raises:
        SchemaMappingError: If any key in `properties` appears in
            PII_PROPERTY_NAMES, listing all offending fields.
    """
    violations = sorted(k for k in properties if k in PII_PROPERTY_NAMES)

    if violations:
        raise SchemaMappingError(
            "Graph property dict contains PII fields that must not be written to the graph",
            pii_fields=violations,
            field_count=len(violations),
        )


def assert_activity_weight_valid(weight: float) -> None:
    """
    Assert that an activity weight value is within the expected range.

    Args:
        weight: The activity weight to validate.

    Raises:
        SchemaMappingError: If the weight is outside [ACTIVITY_WEIGHT_MIN,
            ACTIVITY_WEIGHT_MAX].
    """
    if not (ACTIVITY_WEIGHT_MIN <= weight <= ACTIVITY_WEIGHT_MAX):
        raise SchemaMappingError(
            "activity_weight value is outside expected range",
            weight=weight,
            expected_min=ACTIVITY_WEIGHT_MIN,
            expected_max=ACTIVITY_WEIGHT_MAX,
        )


def assert_write_once_not_overwritten(
    existing_properties: dict[str, Any],
    incoming_properties: dict[str, Any],
) -> None:
    """
    Assert that write-once properties are not being overwritten.

    Intended for use in validation pipelines and loader tests to catch
    pipeline runs that accidentally clobber creation-time properties.

    Args:
        existing_properties: Current property values on the node.
        incoming_properties: New property values about to be applied.

    Raises:
        SchemaMappingError: If any write-once property exists in both dicts
            with different non-null values.
    """
    violations: list[str] = []

    for prop in WRITE_ONCE_PROPERTIES:
        existing_val = existing_properties.get(prop)
        incoming_val = incoming_properties.get(prop)

        if (
            existing_val is not None
            and incoming_val is not None
            and existing_val != incoming_val
        ):
            violations.append(prop)

    if violations:
        raise SchemaMappingError(
            "Attempted to overwrite write-once graph properties",
            write_once_violations=sorted(violations),
        )