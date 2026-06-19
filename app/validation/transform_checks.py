"""
GraphWriteBatch validation — primary quality gate between transform and load layers.

Checks every batch produced by transformers before it reaches a loader.
Never raises; every check returns ValidationResult or list[ValidationResult].
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.contracts.graph_records import GraphWriteBatch
from app.core.constants import GRAPH_NODE_LABELS, GRAPH_RELATIONSHIP_TYPES
from app.schemas.graph.properties import (
    ACTIVITY_WEIGHT_PROPERTY,
    ACTIVITY_WEIGHT_MAX,
    ACTIVITY_WEIGHT_MIN,
    PII_PROPERTY_NAMES,
)
from app.validation.base import BaseValidator, ValidationResult, ValidationSeverity

# TINYINT fields that should have been coerced to bool before graph write.
_TINYINT_FIELD_NAMES: frozenset[str] = frozenset(
    {
        "is_active",
        "is_processed",
        "is_suspended",
        "is_waiting",
        "lockout_enabled",
        "has_early_prediction_permission",
        "is_public",
        "is_read",
        "is_featured",
        "is_verified",
    }
)


class TransformValidator(BaseValidator):
    """Validates a GraphWriteBatch produced by a transformer."""

    def validate(self, batch: GraphWriteBatch) -> list[ValidationResult]:  # type: ignore[override]
        results: list[ValidationResult] = []
        results.extend(self.check_batch_structure(batch))
        results.append(self.check_node_ids_non_empty(batch))
        results.append(self.check_node_labels_registered(batch))
        results.append(self.check_relationship_types_registered(batch))
        results.append(self.check_no_pii_in_node_properties(batch))
        results.append(self.check_no_pii_in_rel_properties(batch))
        results.append(self.check_relationship_endpoints_non_empty(batch))
        results.append(self.check_activity_weights_valid(batch))
        results.extend(self.check_timestamps_are_strings(batch))
        results.extend(self.check_tinyint_coercion(batch))
        results.append(self.check_source_name_consistency(batch))
        return results

    # ── batch-level ────────────────────────────────────────────────────────────

    def check_batch_structure(self, batch: GraphWriteBatch) -> list[ValidationResult]:
        """ERROR if run_id or source_name is empty; ERROR if batch_sequence < 0."""
        name = "check_batch_structure"
        results: list[ValidationResult] = []

        if not batch.pipeline_run_id or not batch.pipeline_run_id.strip():
            results.append(self._fail(name, batch.source_name, ValidationSeverity.ERROR,
                                      "GraphWriteBatch.pipeline_run_id is empty",
                                      field="pipeline_run_id"))
        else:
            results.append(self._pass(name, batch.source_name, "pipeline_run_id is present"))

        if not batch.source_name or not batch.source_name.strip():
            results.append(self._fail(name, "<unknown>", ValidationSeverity.ERROR,
                                      "GraphWriteBatch.source_name is empty",
                                      field="source_name"))
        else:
            results.append(self._pass(name, batch.source_name, "source_name is present"))

        if batch.batch_sequence < 0:
            results.append(self._fail(name, batch.source_name, ValidationSeverity.ERROR,
                                      f"batch_sequence must be >= 0, got {batch.batch_sequence}",
                                      batch_sequence=batch.batch_sequence))
        else:
            results.append(self._pass(name, batch.source_name, "batch_sequence is valid"))

        return results

    # ── node checks ────────────────────────────────────────────────────────────

    def check_node_ids_non_empty(self, batch: GraphWriteBatch) -> ValidationResult:
        """ERROR if any NodeRecord has an empty node_id."""
        name = "check_node_ids_non_empty"
        violations = [i for i, n in enumerate(batch.node_records)
                      if not n.node_id or not n.node_id.strip()]
        if not violations:
            return self._pass(name, batch.source_name,
                              f"All {len(batch.node_records)} node_ids are non-empty")
        return self._fail(name, batch.source_name, ValidationSeverity.ERROR,
                          f"{len(violations)} NodeRecord(s) have empty node_id",
                          violation_count=len(violations),
                          sample_indices=violations[:10])

    def check_node_labels_registered(self, batch: GraphWriteBatch) -> ValidationResult:
        """ERROR if any NodeRecord.label is not in GRAPH_NODE_LABELS."""
        name = "check_node_labels_registered"
        bad_labels = sorted(
            {n.label for n in batch.node_records if n.label not in GRAPH_NODE_LABELS}
        )
        if not bad_labels:
            return self._pass(name, batch.source_name, "All node labels are registered")
        return self._fail(name, batch.source_name, ValidationSeverity.ERROR,
                          f"Unregistered node labels: {bad_labels}",
                          unregistered_labels=bad_labels)

    def check_no_pii_in_node_properties(self, batch: GraphWriteBatch) -> ValidationResult:
        """CRITICAL if any NodeRecord.properties contains a PII field name."""
        name = "check_no_pii_in_node_properties"
        offenders: list[dict[str, Any]] = []
        for node in batch.node_records:
            violations = sorted(k for k in node.properties if k in PII_PROPERTY_NAMES)
            if violations:
                offenders.append({"node_id": node.node_id, "pii_fields": violations})
        if not offenders:
            return self._pass(name, batch.source_name,
                              "No PII found in node properties")
        return self._fail(name, batch.source_name, ValidationSeverity.CRITICAL,
                          f"PII fields found in {len(offenders)} NodeRecord(s)",
                          offender_count=len(offenders),
                          sample=offenders[:5])

    # ── relationship checks ────────────────────────────────────────────────────

    def check_relationship_types_registered(self, batch: GraphWriteBatch) -> ValidationResult:
        """ERROR if any RelationshipRecord.rel_type is not in GRAPH_RELATIONSHIP_TYPES."""
        name = "check_relationship_types_registered"
        bad_types = sorted(
            {r.rel_type for r in batch.relationship_records
             if r.rel_type not in GRAPH_RELATIONSHIP_TYPES}
        )
        if not bad_types:
            return self._pass(name, batch.source_name,
                              "All relationship types are registered")
        return self._fail(name, batch.source_name, ValidationSeverity.ERROR,
                          f"Unregistered relationship types: {bad_types}",
                          unregistered_types=bad_types)

    def check_no_pii_in_rel_properties(self, batch: GraphWriteBatch) -> ValidationResult:
        """CRITICAL if any RelationshipRecord.properties contains a PII field name."""
        name = "check_no_pii_in_rel_properties"
        offenders: list[dict[str, Any]] = []
        for rel in batch.relationship_records:
            violations = sorted(k for k in rel.properties if k in PII_PROPERTY_NAMES)
            if violations:
                offenders.append({"edge": rel.edge_key(), "pii_fields": violations})
        if not offenders:
            return self._pass(name, batch.source_name,
                              "No PII found in relationship properties")
        return self._fail(name, batch.source_name, ValidationSeverity.CRITICAL,
                          f"PII fields found in {len(offenders)} RelationshipRecord(s)",
                          offender_count=len(offenders),
                          sample=offenders[:5])

    def check_relationship_endpoints_non_empty(self, batch: GraphWriteBatch) -> ValidationResult:
        """ERROR if any RelationshipRecord has empty start_node_id or end_node_id."""
        name = "check_relationship_endpoints_non_empty"
        empty_start = sum(1 for r in batch.relationship_records
                          if not r.start_node_id or not r.start_node_id.strip())
        empty_end = sum(1 for r in batch.relationship_records
                        if not r.end_node_id or not r.end_node_id.strip())
        if empty_start == 0 and empty_end == 0:
            return self._pass(name, batch.source_name,
                              "All relationship endpoints are non-empty")
        return self._fail(name, batch.source_name, ValidationSeverity.ERROR,
                          f"{empty_start} empty start_node_id(s), "
                          f"{empty_end} empty end_node_id(s)",
                          empty_start_count=empty_start,
                          empty_end_count=empty_end)

    def check_activity_weights_valid(self, batch: GraphWriteBatch) -> ValidationResult:
        """ERROR if any relationship 'activity_weight' property is outside [0.0, 1.0]."""
        name = "check_activity_weights_valid"
        violations: list[dict[str, Any]] = []
        for rel in batch.relationship_records:
            weight = rel.properties.get(ACTIVITY_WEIGHT_PROPERTY)
            if weight is None:
                continue
            if not isinstance(weight, (int, float)):
                violations.append({"edge": rel.edge_key(), "weight": weight,
                                   "reason": "not numeric"})
            elif not (ACTIVITY_WEIGHT_MIN <= weight <= ACTIVITY_WEIGHT_MAX):
                violations.append({"edge": rel.edge_key(), "weight": weight,
                                   "reason": f"outside [{ACTIVITY_WEIGHT_MIN}, {ACTIVITY_WEIGHT_MAX}]"})
        if not violations:
            return self._pass(name, batch.source_name,
                              "All activity_weight values are valid")
        return self._fail(name, batch.source_name, ValidationSeverity.ERROR,
                          f"{len(violations)} invalid activity_weight value(s)",
                          violation_count=len(violations),
                          sample=violations[:5])

    # ── property-level checks ─────────────────────────────────────────────────

    def check_timestamps_are_strings(self, batch: GraphWriteBatch) -> list[ValidationResult]:
        """WARNING if any property value is a datetime object (not str)."""
        name = "check_timestamps_are_strings"
        results: list[ValidationResult] = []
        offending_labels: dict[str, int] = {}

        for node in batch.node_records:
            for val in node.properties.values():
                if isinstance(val, datetime):
                    offending_labels[node.label] = offending_labels.get(node.label, 0) + 1

        for rel in batch.relationship_records:
            for val in rel.properties.values():
                if isinstance(val, datetime):
                    offending_labels[rel.rel_type] = offending_labels.get(rel.rel_type, 0) + 1

        if not offending_labels:
            results.append(self._pass(name, batch.source_name,
                                      "No raw datetime objects found in properties"))
        else:
            for label, count in offending_labels.items():
                results.append(self._warn(
                    name, batch.source_name,
                    f"{count} property value(s) on '{label}' are datetime objects, not strings",
                    label=label, raw_datetime_count=count,
                ))

        return results

    def check_tinyint_coercion(self, batch: GraphWriteBatch) -> list[ValidationResult]:
        """WARNING if known TINYINT properties are int 0/1 instead of bool."""
        name = "check_tinyint_coercion"
        results: list[ValidationResult] = []
        offending_labels: dict[str, list[str]] = {}

        for node in batch.node_records:
            for prop_name, val in node.properties.items():
                if prop_name in _TINYINT_FIELD_NAMES and isinstance(val, int) and val in (0, 1):
                    offending_labels.setdefault(node.label, [])
                    if prop_name not in offending_labels[node.label]:
                        offending_labels[node.label].append(prop_name)

        for rel in batch.relationship_records:
            for prop_name, val in rel.properties.items():
                if prop_name in _TINYINT_FIELD_NAMES and isinstance(val, int) and val in (0, 1):
                    offending_labels.setdefault(rel.rel_type, [])
                    if prop_name not in offending_labels[rel.rel_type]:
                        offending_labels[rel.rel_type].append(prop_name)

        if not offending_labels:
            results.append(self._pass(name, batch.source_name,
                                      "No unconverted TINYINT values found"))
        else:
            for label, fields in offending_labels.items():
                results.append(self._warn(
                    name, batch.source_name,
                    f"'{label}' has TINYINT fields that should be bool: {fields}",
                    label=label, fields=fields,
                ))

        return results

    def check_skip_rate_acceptable(
        self,
        source_name: str,
        total_input_rows: int,
        skip_count: int,
        max_skip_rate: float = 0.10,
    ) -> ValidationResult:
        """WARNING if skip_count / total_input_rows > max_skip_rate."""
        name = "check_skip_rate_acceptable"
        if total_input_rows == 0:
            return self._pass(name, source_name, "No input rows; skip rate not applicable")
        skip_rate = skip_count / total_input_rows
        if skip_rate <= max_skip_rate:
            return self._pass(name, source_name,
                              f"Skip rate {skip_rate:.1%} is within threshold {max_skip_rate:.1%}",
                              skip_rate=round(skip_rate, 4),
                              skip_count=skip_count,
                              total_input_rows=total_input_rows)
        return self._warn(name, source_name,
                          f"Skip rate {skip_rate:.1%} exceeds max {max_skip_rate:.1%}; "
                          "suggests a systematic transformer issue",
                          skip_rate=round(skip_rate, 4),
                          skip_count=skip_count,
                          total_input_rows=total_input_rows,
                          max_skip_rate=max_skip_rate)

    def check_source_name_consistency(self, batch: GraphWriteBatch) -> ValidationResult:
        """ERROR if any record's source_name differs from batch.source_name."""
        name = "check_source_name_consistency"
        mismatched_nodes = [
            n.node_id for n in batch.node_records
            if n.source_name != batch.source_name
        ]
        mismatched_rels = [
            r.edge_key() for r in batch.relationship_records
            if r.source_name != batch.source_name
        ]
        if not mismatched_nodes and not mismatched_rels:
            return self._pass(name, batch.source_name,
                              "All record source_names match batch source_name")
        return self._fail(name, batch.source_name, ValidationSeverity.ERROR,
                          f"{len(mismatched_nodes)} node(s) and {len(mismatched_rels)} rel(s) "
                          "have a mismatched source_name",
                          mismatched_node_count=len(mismatched_nodes),
                          mismatched_rel_count=len(mismatched_rels),
                          sample_nodes=mismatched_nodes[:5],
                          sample_rels=mismatched_rels[:5])


def validate_graph_write_batch(
    batch: GraphWriteBatch,
    run_id: str,
    total_input_rows: int | None = None,
    skip_count: int | None = None,
    max_skip_rate: float = 0.10,
) -> list[ValidationResult]:
    """Module-level convenience: construct TransformValidator and run validate()."""
    validator = TransformValidator(run_id)
    results = validator.validate(batch)

    if total_input_rows is not None and skip_count is not None:
        results.append(validator.check_skip_rate_acceptable(
            batch.source_name, total_input_rows, skip_count, max_skip_rate,
        ))

    return results