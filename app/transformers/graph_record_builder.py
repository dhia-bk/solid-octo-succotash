"""
app/transformers/graph_record_builder.py
=========================================
Thin wrapper around the graph_records.py factory functions.

Pre-fills run_id and source_name so domain transformers never repeat
those arguments. Every domain transformer must use this — never call
build_node_record(), build_relationship_record(), or build_graph_write_batch()
directly.

Usage:
    builder = GraphRecordBuilder(self._run_id, SOURCE_NAME)

    node = builder.node(USER, user_id, properties)
    rel  = builder.rel(PREDICTED, user_id, fixture_id,
                       start_label=USER, end_label=MATCH,
                       properties={"predicted_at": "..."})
    batch = builder.batch(nodes, rels, batch_sequence=0)
"""

from __future__ import annotations

from typing import Any

from app.contracts.graph_records import (
    GraphWriteBatch,
    NodeRecord,
    RelationshipRecord,
    build_graph_write_batch,
    build_node_record,
    build_relationship_record,
)
from app.core.exceptions import TransformationError


class GraphRecordBuilder:
    """
    Pre-fills run_id and source_name on every graph record factory call.

    One instance is created per transformer.transform() call:
        builder = GraphRecordBuilder(self._run_id, SOURCE_NAME)

    The builder holds no mutable state beyond the two constructor arguments.
    """

    def __init__(self, run_id: str, source_name: str) -> None:
        """
        Args:
            run_id:      Pipeline run ID. Written to every produced record.
            source_name: Logical warehouse source/table name. Written to
                         every produced record.

        Raises:
            TransformationError: If either argument is empty.
        """
        if not run_id or not run_id.strip():
            raise TransformationError(
                "GraphRecordBuilder requires a non-empty run_id",
                source_name=source_name,
            )
        if not source_name or not source_name.strip():
            raise TransformationError(
                "GraphRecordBuilder requires a non-empty source_name",
                run_id=run_id,
            )

        self._run_id = run_id
        self._source_name = source_name

    # -- Node -----------------------------------------------------------------

    def node(
        self,
        label: str,
        node_id: str,
        properties: dict[str, Any],
        weighting_version: str | None = None,
    ) -> NodeRecord:
        """
        Build a validated NodeRecord with run_id and source_name pre-filled.

        Delegates to build_node_record(). PII validation runs at
        NodeRecord.__post_init__ — any PII field in properties raises
        SchemaMappingError immediately.

        Args:
            label:             Graph node label. Must be in GRAPH_NODE_LABELS.
            node_id:           Stable graph node identifier from ids.py.
            properties:        Node property dict. Must be PII-free.
            weighting_version: Optional weighting version marker.

        Returns:
            Validated NodeRecord.

        Raises:
            ValidationError:    If the record fails structural validation.
            SchemaMappingError: If properties contains a PII field.
        """
        return build_node_record(
            label=label,
            node_id=node_id,
            properties=properties,
            run_id=self._run_id,
            source_name=self._source_name,
            weighting_version=weighting_version,
        )

    # -- Relationship ---------------------------------------------------------

    def rel(
        self,
        rel_type: str,
        start_node_id: str,
        end_node_id: str,
        *,
        start_label: str,
        end_label: str,
        properties: dict[str, Any] | None = None,
    ) -> RelationshipRecord:
        """
        Build a validated RelationshipRecord with run_id and source_name
        pre-filled.

        Delegates to build_relationship_record(). PII validation runs at
        RelationshipRecord.__post_init__.

        Args:
            rel_type:      Relationship type. Must be in GRAPH_RELATIONSHIP_TYPES.
            start_node_id: Graph node ID of the start node.
            end_node_id:   Graph node ID of the end node.
            start_label:   Node label of the start node.
            end_label:     Node label of the end node.
            properties:    Optional relationship properties. Must be PII-free.
                           Defaults to empty dict.

        Returns:
            Validated RelationshipRecord.

        Raises:
            ValidationError:    If the record fails structural validation.
            SchemaMappingError: If properties contains a PII field.
        """
        return build_relationship_record(
            rel_type=rel_type,
            start_node_id=start_node_id,
            end_node_id=end_node_id,
            start_label=start_label,
            end_label=end_label,
            run_id=self._run_id,
            source_name=self._source_name,
            properties=properties,
        )

    # -- Batch ----------------------------------------------------------------

    def batch(
        self,
        node_records: list[NodeRecord],
        relationship_records: list[RelationshipRecord],
        batch_sequence: int,
    ) -> GraphWriteBatch:
        """
        Assemble a validated GraphWriteBatch with run_id and source_name
        pre-filled.

        Delegates to build_graph_write_batch().

        Args:
            node_records:           NodeRecord instances for this batch.
            relationship_records:   RelationshipRecord instances for this batch.
            batch_sequence:         Ordinal position of this batch within the
                                    pipeline run (>= 0).

        Returns:
            Validated GraphWriteBatch ready for the loader layer.

        Raises:
            ValidationError: If batch-level fields are invalid.
        """
        return build_graph_write_batch(
            run_id=self._run_id,
            source_name=self._source_name,
            node_records=node_records,
            relationship_records=relationship_records,
            batch_sequence=batch_sequence,
        )

    # -- Repr -----------------------------------------------------------------

    def __repr__(self) -> str:
        return (
            f"GraphRecordBuilder("
            f"source={self._source_name!r}, "
            f"run_id={self._run_id!r})"
        )