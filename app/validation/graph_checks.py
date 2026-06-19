"""
Neo4j graph state validation — read-only queries only, no writes.

Checks that expected nodes/relationships exist, constraints are satisfied,
and property distributions look healthy.
"""

from __future__ import annotations

from typing import Any

from app.contracts.graph_records import GraphWriteBatch
from app.db.neo4j_client import Neo4jClient
from app.schemas.graph.constraints import  get_all_constraints
from app.validation.base import BaseValidator, ValidationResult, ValidationSeverity

CONSTRAINT_DECLARATIONS = get_all_constraints()

class GraphValidator(BaseValidator):
    """Validates graph state via read-only Cypher queries."""

    def __init__(self, run_id: str, neo4j_client: Neo4jClient) -> None:
        super().__init__(run_id)
        self._client = neo4j_client

    def validate(self, *args: Any, **kwargs: Any) -> list[ValidationResult]:
        raise NotImplementedError(
            "Use specific check methods or run_post_load_checks() instead."
        )

    # ── node existence / count ─────────────────────────────────────────────────

    def validate_node_exists(self, node_id: str, label: str) -> ValidationResult:
        """ERROR if no node with the given id and label exists in the graph."""
        name = "validate_node_exists"
        query = f"MATCH (n:{label} {{id: $node_id}}) RETURN count(n) AS cnt"
        try:
            records = self._client.query_many(query, {"node_id": node_id})
            count = records[0]["cnt"] if records else 0
        except Exception as exc:
            return self._fail(name, label, ValidationSeverity.ERROR,
                              f"Query failed while checking node existence: {exc}",
                              node_id=node_id, label=label)
        if count > 0:
            return self._pass(name, label, f"Node ({label} id={node_id!r}) exists")
        return self._fail(name, label, ValidationSeverity.ERROR,
                          f"Node ({label} id={node_id!r}) not found in graph",
                          node_id=node_id, label=label)

    def validate_node_count(self, label: str, expected_min: int) -> ValidationResult:
        """WARNING if node count for label is below expected_min."""
        name = "validate_node_count"
        query = f"MATCH (n:{label}) RETURN count(n) AS cnt"
        try:
            records = self._client.query_many(query)
            count = records[0]["cnt"] if records else 0
        except Exception as exc:
            return self._fail(name, label, ValidationSeverity.ERROR,
                              f"Query failed while counting nodes: {exc}",
                              label=label)
        if count >= expected_min:
            return self._pass(name, label,
                              f"{label} has {count} nodes (expected >= {expected_min})",
                              node_count=count)
        return self._warn(name, label,
                          f"{label} has {count} nodes; expected >= {expected_min}",
                          node_count=count, expected_min=expected_min)

    # ── relationship existence ─────────────────────────────────────────────────

    def validate_relationship_exists(
        self, start_id: str, end_id: str, rel_type: str,
    ) -> ValidationResult:
        """ERROR if no relationship of the given type exists between the two node ids."""
        name = "validate_relationship_exists"
        query = (
            f"MATCH (a {{id: $start_id}})-[r:{rel_type}]->(b {{id: $end_id}}) "
            "RETURN count(r) AS cnt"
        )
        try:
            records = self._client.query_many(query, {"start_id": start_id, "end_id": end_id})
            count = records[0]["cnt"] if records else 0
        except Exception as exc:
            return self._fail(name, rel_type, ValidationSeverity.ERROR,
                              f"Query failed while checking relationship existence: {exc}",
                              rel_type=rel_type, start_id=start_id, end_id=end_id)
        if count > 0:
            return self._pass(name, rel_type,
                              f"Relationship {start_id}-[{rel_type}]->{end_id} exists")
        return self._fail(name, rel_type, ValidationSeverity.ERROR,
                          f"Relationship {start_id}-[{rel_type}]->{end_id} not found",
                          rel_type=rel_type, start_id=start_id, end_id=end_id)

    # ── property quality ───────────────────────────────────────────────────────

    def validate_property_non_null(
        self, label: str, property_name: str, sample_size: int = 1000,
    ) -> ValidationResult:
        """WARNING if more than 5% of sampled nodes have null for the given property."""
        name = "validate_property_non_null"
        query = (
            f"MATCH (n:{label}) WITH n LIMIT $sample_size "
            f"RETURN count(n) AS total, "
            f"count(n.{property_name}) AS non_null_count"
        )
        try:
            records = self._client.query_many(query, {"sample_size": sample_size})
            row = records[0] if records else {"total": 0, "non_null_count": 0}
            total = row["total"]
            non_null = row["non_null_count"]
        except Exception as exc:
            return self._fail(name, label, ValidationSeverity.ERROR,
                              f"Query failed while checking property nulls: {exc}",
                              label=label, property_name=property_name)

        if total == 0:
            return self._pass(name, label, f"No {label} nodes sampled")

        null_rate = (total - non_null) / total
        if null_rate <= 0.05:
            return self._pass(name, label,
                              f"{property_name} null rate {null_rate:.1%} is acceptable",
                              null_rate=round(null_rate, 4), sample_size=total)
        return self._warn(name, label,
                          f"{property_name} null rate {null_rate:.1%} exceeds 5% in sample",
                          property_name=property_name,
                          null_rate=round(null_rate, 4),
                          null_count=total - non_null,
                          sample_size=total)

    def validate_no_orphaned_relationships(self, rel_type: str) -> ValidationResult:
        """ERROR if any relationship of the given type has a missing start or end node."""
        name = "validate_no_orphaned_relationships"
        query = (
            f"MATCH ()-[r:{rel_type}]->() "
            "WHERE startNode(r) IS NULL OR endNode(r) IS NULL "
            "RETURN count(r) AS cnt"
        )
        try:
            records = self._client.query_many(query)
            count = records[0]["cnt"] if records else 0
        except Exception as exc:
            return self._fail(name, rel_type, ValidationSeverity.ERROR,
                              f"Query failed while checking orphaned relationships: {exc}",
                              rel_type=rel_type)
        if count == 0:
            return self._pass(name, rel_type,
                              f"No orphaned {rel_type} relationships found")
        return self._fail(name, rel_type, ValidationSeverity.ERROR,
                          f"{count} orphaned {rel_type} relationship(s) found",
                          rel_type=rel_type, orphan_count=count)

    # ── schema / index checks ──────────────────────────────────────────────────

    def validate_constraint_satisfied(self, constraint_name: str) -> ValidationResult:
        """ERROR if a declared constraint is not present in the graph schema."""
        name = "validate_constraint_satisfied"
        query = (
            "SHOW CONSTRAINTS WHERE name = $constraint_name "
            "RETURN count(*) AS cnt"
        )
        try:
            records = self._client.query_many(query, {"constraint_name": constraint_name})
            count = records[0]["cnt"] if records else 0
        except Exception as exc:
            return self._fail(name, constraint_name, ValidationSeverity.ERROR,
                              f"Query failed while checking constraint: {exc}",
                              constraint_name=constraint_name)
        if count > 0:
            return self._pass(name, constraint_name,
                              f"Constraint '{constraint_name}' is present")
        return self._fail(name, constraint_name, ValidationSeverity.ERROR,
                          f"Constraint '{constraint_name}' is not present in graph schema",
                          constraint_name=constraint_name)

    def validate_index_present(self, label: str, property_name: str) -> ValidationResult:
        """WARNING if the expected index on label/property is not present."""
        name = "validate_index_present"
        query = (
            "SHOW INDEXES WHERE labelsOrTypes = [$label] AND properties = [$property] "
            "RETURN count(*) AS cnt"
        )
        try:
            records = self._client.query_many(query, {"label": label, "property": property_name})
            count = records[0]["cnt"] if records else 0
        except Exception as exc:
            return self._fail(name, label, ValidationSeverity.ERROR,
                              f"Query failed while checking index: {exc}",
                              label=label, property_name=property_name)
        if count > 0:
            return self._pass(name, label,
                              f"Index on ({label}).{property_name} is present")
        return self._warn(name, label,
                          f"Index on ({label}).{property_name} not found",
                          label=label, property_name=property_name)

    def validate_node_property_distribution(
        self, label: str, property_name: str, top_n: int = 10,
    ) -> ValidationResult:
        """INFO result carrying the property value distribution (top-N values and counts)."""
        name = "validate_node_property_distribution"
        query = (
            f"MATCH (n:{label}) WHERE n.{property_name} IS NOT NULL "
            f"WITH n.{property_name} AS val, count(*) AS cnt "
            "ORDER BY cnt DESC "
            "LIMIT $top_n "
            "RETURN collect({value: val, count: cnt}) AS distribution"
        )
        try:
            records = self._client.query_many(query, {"top_n": top_n})
            distribution = records[0]["distribution"] if records else []
        except Exception as exc:
            return self._fail(name, label, ValidationSeverity.ERROR,
                              f"Query failed while computing distribution: {exc}",
                              label=label, property_name=property_name)
        return ValidationResult(
            check_name=name,
            passed=True,
            severity=ValidationSeverity.INFO,
            source=label,
            message=f"Property distribution for ({label}).{property_name}",
            details={"label": label, "property_name": property_name,
                     "distribution": distribution},
            run_id=self._run_id,
        )

    # ── post-load suite ────────────────────────────────────────────────────────

    def run_post_load_checks(
        self, source_name: str, batch: GraphWriteBatch,
    ) -> list[ValidationResult]:
        """Spot-sample node existence for all records in the batch."""
        results: list[ValidationResult] = []
        sample_ids = [n.node_id for n in batch.node_records[:20]]
        for node in batch.node_records[:20]:
            results.append(self.validate_node_exists(node.node_id, node.label))

        for constraint in CONSTRAINT_DECLARATIONS:
            results.append(self.validate_constraint_satisfied(constraint.name))

        return results