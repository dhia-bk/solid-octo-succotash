"""
Typed contract layer for graph write payloads.

This module defines the records that transformers produce and loaders consume.
No transformer may pass a raw dict to a loader. Every graph write must be
traceable to a typed, validated record.

Design rules:
- NodeRecord and RelationshipRecord are the only permitted inter-layer payloads.
- PII validation is enforced at the NodeRecord and RelationshipRecord creation
  boundary via assert_no_pii() from app.schemas.graph.properties.
- All label values must be drawn from constants.GRAPH_NODE_LABELS.
- All rel_type values must be drawn from constants.GRAPH_RELATIONSHIP_TYPES.
- Loaders receive GraphWriteBatch and return GraphWriteResult — nothing else.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from app.core.constants import (
    GRAPH_NODE_LABELS,
    GRAPH_RELATIONSHIP_TYPES,
)
from app.core.exceptions import ValidationError
from app.core.time import format_iso_timestamp, utc_now
from app.schemas.graph.properties import assert_no_pii


# NodeRecord

@dataclass(frozen=True)
class NodeRecord:
    """
    Typed payload for a single graph node write operation.

    Produced by transformers, consumed by loaders. No raw dicts permitted
    at this boundary.

    Attributes:
        label:             Graph node label. Must be in GRAPH_NODE_LABELS.
        node_id:           Stable, deterministic graph node identifier.
        properties:        Node property dict. Must be PII-free.
        pipeline_run_id:   Run ID of the owning pipeline execution.
        weighting_version: Version marker of the weighting model, if applicable.
        loaded_at:         ISO UTC timestamp of record production.
        source_name:       Logical source/table that produced this record.
    """

    label: str
    node_id: str
    properties: dict[str, Any]
    pipeline_run_id: str
    weighting_version: str | None
    loaded_at: str
    source_name: str

    def __post_init__(self) -> None:
        errors = validate_node_record(self)
        if errors:
            raise ValidationError(
                "NodeRecord failed validation",
                errors=errors,
                label=self.label,
                node_id=self.node_id,
            )

    def has_weighting(self) -> bool:
        """Return True if a weighting version is attached to this record."""
        return self.weighting_version is not None

    def property_count(self) -> int:
        """Return the number of properties on this record."""
        return len(self.properties)


# RelationshipRecord

@dataclass(frozen=True)
class RelationshipRecord:
    """
    Typed payload for a single graph relationship write operation.

    Produced by transformers, consumed by loaders.

    Attributes:
        rel_type:        Relationship type. Must be in GRAPH_RELATIONSHIP_TYPES.
        start_node_id:   Graph node ID of the relationship start node.
        end_node_id:     Graph node ID of the relationship end node.
        start_label:     Node label of the start node.
        end_label:       Node label of the end node.
        properties:      Relationship property dict. Must be PII-free.
        pipeline_run_id: Run ID of the owning pipeline execution.
        source_name:     Logical source/table that produced this record.
    """

    rel_type: str
    start_node_id: str
    end_node_id: str
    start_label: str
    end_label: str
    properties: dict[str, Any]
    pipeline_run_id: str
    source_name: str

    def __post_init__(self) -> None:
        errors = validate_relationship_record(self)
        if errors:
            raise ValidationError(
                "RelationshipRecord failed validation",
                errors=errors,
                rel_type=self.rel_type,
                start_node_id=self.start_node_id,
                end_node_id=self.end_node_id,
            )

    def edge_key(self) -> str:
        """
        Return a human-readable edge descriptor for logs and error messages.

        Format: (StartLabel)-[REL_TYPE]->(EndLabel)
        """
        return f"({self.start_label})-[{self.rel_type}]->({self.end_label})"

    def has_properties(self) -> bool:
        """Return True if this relationship carries any properties."""
        return bool(self.properties)



# GraphWriteBatch

@dataclass(frozen=True)
class GraphWriteBatch:
    """
    Typed container for a batch of node and relationship records to write.

    Produced by transformers, consumed by loaders. Every batch is uniquely
    identified and sequenced within a pipeline run.

    Attributes:
        pipeline_run_id:        Run ID of the owning pipeline execution.
        source_name:            Logical source/table that produced this batch.
        node_records:           Typed NodeRecord instances to write.
        relationship_records:   Typed RelationshipRecord instances to write.
        batch_id:               Unique identifier for this batch.
        batch_sequence:         Ordinal position of this batch within the run.
        produced_at:            ISO UTC timestamp when this batch was assembled.
    """

    pipeline_run_id: str
    source_name: str
    node_records: list[NodeRecord]
    relationship_records: list[RelationshipRecord]
    batch_id: str
    batch_sequence: int
    produced_at: str

    def __post_init__(self) -> None:
        _validate_graph_write_batch_fields(self)

    def is_empty(self) -> bool:
        """Return True if this batch contains no node or relationship records."""
        return not self.node_records and not self.relationship_records

    def total_record_count(self) -> int:
        """Return the combined count of node and relationship records."""
        return len(self.node_records) + len(self.relationship_records)

    def node_count(self) -> int:
        """Return the number of node records in this batch."""
        return len(self.node_records)

    def relationship_count(self) -> int:
        """Return the number of relationship records in this batch."""
        return len(self.relationship_records)


# GraphWriteResult

@dataclass(frozen=True)
class GraphWriteResult:
    """
    Result record for a completed graph batch write operation.

    Returned by loaders to the pipeline layer.

    Attributes:
        batch_id:               Batch ID this result corresponds to.
        nodes_created:          Nodes created (not previously existing).
        nodes_merged:           Nodes merged (already existed, properties updated).
        relationships_created:  Relationships created.
        relationships_merged:   Relationships merged (already existed).
        properties_set:         Total property assignments performed.
        duration_ms:            Wall-clock duration of the write in milliseconds.
        status:                 "success", "partial", or "failed".
        error_message:          Error detail for non-success statuses.
    """

    batch_id: str
    nodes_created: int
    nodes_merged: int
    relationships_created: int
    relationships_merged: int
    properties_set: int
    duration_ms: int
    status: str
    error_message: str | None

    def __post_init__(self) -> None:
        _validate_graph_write_result_fields(self)

    def is_successful(self) -> bool:
        """Return True if the write completed without error."""
        return self.status == "success"

    def is_failed(self) -> bool:
        """Return True if the write failed entirely."""
        return self.status == "failed"

    def is_partial(self) -> bool:
        """Return True if the write completed with partial data."""
        return self.status == "partial"

    def total_writes(self) -> int:
        """Return total nodes and relationships touched (created + merged)."""
        return (
            self.nodes_created
            + self.nodes_merged
            + self.relationships_created
            + self.relationships_merged
        )


# Validation helpers (public)

def validate_node_record(record: NodeRecord) -> list[str]:
    """
    Validate a NodeRecord and return a list of error strings.

    Checks performed:
    - label is registered in GRAPH_NODE_LABELS
    - node_id is non-empty
    - source_name is non-empty
    - pipeline_run_id is non-empty
    - loaded_at is non-empty
    - properties contains no PII fields (via assert_no_pii)

    Args:
        record: NodeRecord to validate.

    Returns:
        List of error strings. Empty list means the record is valid.
    """
    errors: list[str] = []

    if record.label not in GRAPH_NODE_LABELS:
        errors.append(
            f"label '{record.label}' is not registered in GRAPH_NODE_LABELS"
        )

    if not record.node_id or not record.node_id.strip():
        errors.append("node_id cannot be empty")

    if not record.source_name or not record.source_name.strip():
        errors.append("source_name cannot be empty")

    if not record.pipeline_run_id or not record.pipeline_run_id.strip():
        errors.append("pipeline_run_id cannot be empty")

    if not record.loaded_at or not record.loaded_at.strip():
        errors.append("loaded_at cannot be empty")

    # PII check via assert_no_pii from app.schemas.graph.properties.
    # SchemaMappingError is caught here and surfaced as a validation error
    # string so callers receive the full error list rather than a hard raise.
    try:
        assert_no_pii(record.properties)
    except Exception as exc:  # noqa: BLE001
        errors.append(f"PII violation in node properties: {exc}")

    return errors


def validate_relationship_record(record: RelationshipRecord) -> list[str]:
    """
    Validate a RelationshipRecord and return a list of error strings.

    Checks performed:
    - rel_type is registered in GRAPH_RELATIONSHIP_TYPES
    - start_node_id is non-empty
    - end_node_id is non-empty
    - start_label is registered in GRAPH_NODE_LABELS
    - end_label is registered in GRAPH_NODE_LABELS
    - source_name is non-empty
    - pipeline_run_id is non-empty
    - properties contains no PII fields (via assert_no_pii)

    Args:
        record: RelationshipRecord to validate.

    Returns:
        List of error strings. Empty list means the record is valid.
    """
    errors: list[str] = []

    if record.rel_type not in GRAPH_RELATIONSHIP_TYPES:
        errors.append(
            f"rel_type '{record.rel_type}' is not registered in GRAPH_RELATIONSHIP_TYPES"
        )

    if not record.start_node_id or not record.start_node_id.strip():
        errors.append("start_node_id cannot be empty")

    if not record.end_node_id or not record.end_node_id.strip():
        errors.append("end_node_id cannot be empty")

    if record.start_label not in GRAPH_NODE_LABELS:
        errors.append(
            f"start_label '{record.start_label}' is not registered in GRAPH_NODE_LABELS"
        )

    if record.end_label not in GRAPH_NODE_LABELS:
        errors.append(
            f"end_label '{record.end_label}' is not registered in GRAPH_NODE_LABELS"
        )

    if not record.source_name or not record.source_name.strip():
        errors.append("source_name cannot be empty")

    if not record.pipeline_run_id or not record.pipeline_run_id.strip():
        errors.append("pipeline_run_id cannot be empty")

    try:
        assert_no_pii(record.properties)
    except Exception as exc:  # noqa: BLE001
        errors.append(f"PII violation in relationship properties: {exc}")

    return errors


def validate_graph_write_batch(batch: GraphWriteBatch) -> list[str]:
    """
    Validate a GraphWriteBatch and return all error strings across all records.

    Validates:
    - batch-level fields (pipeline_run_id, source_name, batch_id, batch_sequence)
    - every NodeRecord in node_records
    - every RelationshipRecord in relationship_records

    Error strings from child records are prefixed with their position and
    identifier for easy triage.

    Args:
        batch: GraphWriteBatch to validate.

    Returns:
        Flat list of all error strings. Empty list means the batch is valid.
    """
    errors: list[str] = []

    if not batch.pipeline_run_id or not batch.pipeline_run_id.strip():
        errors.append("GraphWriteBatch.pipeline_run_id cannot be empty")

    if not batch.source_name or not batch.source_name.strip():
        errors.append("GraphWriteBatch.source_name cannot be empty")

    if not batch.batch_id or not batch.batch_id.strip():
        errors.append("GraphWriteBatch.batch_id cannot be empty")

    if batch.batch_sequence < 0:
        errors.append(
            f"GraphWriteBatch.batch_sequence must be >= 0, got {batch.batch_sequence}"
        )

    if not batch.produced_at or not batch.produced_at.strip():
        errors.append("GraphWriteBatch.produced_at cannot be empty")

    for i, node_record in enumerate(batch.node_records):
        node_errors = validate_node_record(node_record)
        for error in node_errors:
            errors.append(f"node_records[{i}] (id={node_record.node_id!r}): {error}")

    for i, rel_record in enumerate(batch.relationship_records):
        rel_errors = validate_relationship_record(rel_record)
        for error in rel_errors:
            errors.append(
                f"relationship_records[{i}] ({rel_record.edge_key()}): {error}"
            )

    return errors


# Internal field validators

def _validate_graph_write_batch_fields(batch: GraphWriteBatch) -> None:
    """
    Validate GraphWriteBatch structural fields at construction time.

    Raises:
        ValidationError: On the first structural violation found.
    """
    if not batch.pipeline_run_id or not batch.pipeline_run_id.strip():
        raise ValidationError(
            "GraphWriteBatch.pipeline_run_id cannot be empty",
            field="pipeline_run_id",
        )

    if not batch.source_name or not batch.source_name.strip():
        raise ValidationError(
            "GraphWriteBatch.source_name cannot be empty",
            field="source_name",
        )

    if not batch.batch_id or not batch.batch_id.strip():
        raise ValidationError(
            "GraphWriteBatch.batch_id cannot be empty",
            field="batch_id",
        )

    if batch.batch_sequence < 0:
        raise ValidationError(
            "GraphWriteBatch.batch_sequence must be >= 0",
            field="batch_sequence",
            value=batch.batch_sequence,
        )

    if not batch.produced_at or not batch.produced_at.strip():
        raise ValidationError(
            "GraphWriteBatch.produced_at cannot be empty",
            field="produced_at",
        )


def _validate_graph_write_result_fields(result: GraphWriteResult) -> None:
    """
    Validate GraphWriteResult fields at construction time.

    Raises:
        ValidationError: On the first invalid field found.
    """
    valid_statuses = {"success", "partial", "failed"}

    if not result.batch_id or not result.batch_id.strip():
        raise ValidationError(
            "GraphWriteResult.batch_id cannot be empty",
            field="batch_id",
        )

    if result.status not in valid_statuses:
        raise ValidationError(
            "GraphWriteResult.status must be one of: success, partial, failed",
            field="status",
            value=result.status,
        )

    if result.status in {"partial", "failed"} and not result.error_message:
        raise ValidationError(
            "GraphWriteResult.error_message is required when status is partial or failed",
            field="error_message",
            status=result.status,
        )

    for field_name in (
        "nodes_created",
        "nodes_merged",
        "relationships_created",
        "relationships_merged",
        "properties_set",
        "duration_ms",
    ):
        value = getattr(result, field_name)
        if value < 0:
            raise ValidationError(
                f"GraphWriteResult.{field_name} cannot be negative",
                field=field_name,
                value=value,
            )


# Factory helpers

def _generate_batch_id() -> str:
    """Generate a unique graph write batch ID."""
    return f"gwb-{uuid.uuid4().hex[:16]}"


def build_node_record(
    label: str,
    node_id: str,
    properties: dict[str, Any],
    *,
    run_id: str,
    source_name: str,
    weighting_version: str | None = None,
    loaded_at: str | None = None,
) -> NodeRecord:
    """
    Construct a validated NodeRecord.

    PII validation runs at construction time via NodeRecord.__post_init__.

    Args:
        label:             Graph node label. Must be in GRAPH_NODE_LABELS.
        node_id:           Stable graph node identifier.
        properties:        Node properties. Must be PII-free.
        run_id:            Pipeline run ID.
        source_name:       Logical source/table name.
        weighting_version: Optional weighting version marker.
        loaded_at:         Optional ISO timestamp. Defaults to utc_now().

    Returns:
        Validated NodeRecord.

    Raises:
        ValidationError: If the record fails any validation check.
    """
    return NodeRecord(
        label=label,
        node_id=node_id,
        properties=properties,
        pipeline_run_id=run_id,
        weighting_version=weighting_version,
        loaded_at=loaded_at or format_iso_timestamp(utc_now()),
        source_name=source_name,
    )


def build_relationship_record(
    rel_type: str,
    start_node_id: str,
    end_node_id: str,
    *,
    start_label: str,
    end_label: str,
    run_id: str,
    source_name: str,
    properties: dict[str, Any] | None = None,
) -> RelationshipRecord:
    """
    Construct a validated RelationshipRecord.

    PII validation runs at construction time via RelationshipRecord.__post_init__.

    Args:
        rel_type:       Relationship type. Must be in GRAPH_RELATIONSHIP_TYPES.
        start_node_id:  Graph node ID of the start node.
        end_node_id:    Graph node ID of the end node.
        start_label:    Node label of the start node.
        end_label:      Node label of the end node.
        run_id:         Pipeline run ID.
        source_name:    Logical source/table name.
        properties:     Optional relationship properties. Must be PII-free.
                        Defaults to empty dict.

    Returns:
        Validated RelationshipRecord.

    Raises:
        ValidationError: If the record fails any validation check.
    """
    return RelationshipRecord(
        rel_type=rel_type,
        start_node_id=start_node_id,
        end_node_id=end_node_id,
        start_label=start_label,
        end_label=end_label,
        properties=properties or {},
        pipeline_run_id=run_id,
        source_name=source_name,
    )


def build_graph_write_batch(
    *,
    run_id: str,
    source_name: str,
    node_records: list[NodeRecord],
    relationship_records: list[RelationshipRecord],
    batch_sequence: int,
    batch_id: str | None = None,
    produced_at: str | None = None,
) -> GraphWriteBatch:
    """
    Construct a GraphWriteBatch from pre-validated node and relationship records.

    Args:
        run_id:                 Pipeline run ID.
        source_name:            Logical source/table name.
        node_records:           List of NodeRecord instances.
        relationship_records:   List of RelationshipRecord instances.
        batch_sequence:         Ordinal sequence number for this batch (>= 0).
        batch_id:               Optional explicit batch ID. Auto-generated if omitted.
        produced_at:            Optional ISO timestamp. Defaults to utc_now().

    Returns:
        Validated GraphWriteBatch.

    Raises:
        ValidationError: If batch-level fields are invalid.
    """
    return GraphWriteBatch(
        pipeline_run_id=run_id,
        source_name=source_name,
        node_records=node_records,
        relationship_records=relationship_records,
        batch_id=batch_id or _generate_batch_id(),
        batch_sequence=batch_sequence,
        produced_at=produced_at or format_iso_timestamp(utc_now()),
    )


def build_graph_write_result(
    *,
    batch_id: str,
    nodes_created: int = 0,
    nodes_merged: int = 0,
    relationships_created: int = 0,
    relationships_merged: int = 0,
    properties_set: int = 0,
    duration_ms: int = 0,
    status: str = "success",
    error_message: str | None = None,
) -> GraphWriteResult:
    """
    Construct a GraphWriteResult returned by a loader after a write operation.

    Args:
        batch_id:               Batch ID this result corresponds to.
        nodes_created:          Count of newly created nodes.
        nodes_merged:           Count of merged (updated) nodes.
        relationships_created:  Count of newly created relationships.
        relationships_merged:   Count of merged relationships.
        properties_set:         Count of property assignments performed.
        duration_ms:            Write duration in milliseconds.
        status:                 "success", "partial", or "failed".
        error_message:          Required for partial or failed status.

    Returns:
        Validated GraphWriteResult.

    Raises:
        ValidationError: If any field is invalid.
    """
    return GraphWriteResult(
        batch_id=batch_id,
        nodes_created=nodes_created,
        nodes_merged=nodes_merged,
        relationships_created=relationships_created,
        relationships_merged=relationships_merged,
        properties_set=properties_set,
        duration_ms=duration_ms,
        status=status,
        error_message=error_message,
    )


def build_failed_write_result(
    *,
    batch_id: str,
    error_message: str,
    duration_ms: int = 0,
) -> GraphWriteResult:
    """
    Convenience constructor for a fully failed graph write result.

    Args:
        batch_id:      Batch ID this result corresponds to.
        error_message: Required error description.
        duration_ms:   Duration up to failure point in milliseconds.

    Returns:
        GraphWriteResult with status="failed".
    """
    return build_graph_write_result(
        batch_id=batch_id,
        status="failed",
        error_message=error_message,
        duration_ms=duration_ms,
    )