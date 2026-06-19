"""
GDS projection and analytics output validation.

Validates that the in-memory graph projection exists and is populated,
and that Leiden / PageRank / inference outputs meet minimum quality thresholds.
"""

from __future__ import annotations

from typing import Any

from app.core.config import get_settings
from app.core.constants import (
    DEFAULT_LEIDEN_WRITE_PROPERTY,
    DEFAULT_MEMBERSHIP_ACTIVITY_WEIGHT_PROPERTY,
    DEFAULT_PAGERANK_WRITE_PROPERTY,
    PERSONA_STATE,
    USER,
)
from app.db.neo4j_client import Neo4jClient
from app.validation.base import BaseValidator, ValidationResult, ValidationSeverity


class AnalyticsValidator(BaseValidator):
    """Validates GDS projection state and analytics output records."""

    def __init__(self, run_id: str, neo4j_client: Neo4jClient) -> None:
        super().__init__(run_id)
        self._client = neo4j_client

    def validate(self, *args: Any, **kwargs: Any) -> list[ValidationResult]:
        raise NotImplementedError(
            "Use specific check methods on AnalyticsValidator directly."
        )

    # ── GDS projection checks ──────────────────────────────────────────────────

    def check_gds_projection_exists(self, graph_name: str) -> ValidationResult:
        """ERROR if the named GDS in-memory graph projection does not exist."""
        name = "check_gds_projection_exists"
        query = (
            "CALL gds.graph.exists($graph_name) YIELD exists "
            "RETURN exists"
        )
        try:
            records = self._client.query_many(query, {"graph_name": graph_name})
            exists = records[0]["exists"] if records else False
        except Exception as exc:
            return self._fail(name, graph_name, ValidationSeverity.ERROR,
                              f"GDS query failed while checking projection existence: {exc}",
                              graph_name=graph_name)
        if exists:
            return self._pass(name, graph_name,
                              f"GDS projection '{graph_name}' exists")
        return self._fail(name, graph_name, ValidationSeverity.ERROR,
                          f"GDS projection '{graph_name}' does not exist",
                          graph_name=graph_name)

    def check_gds_node_count(
        self, graph_name: str, expected_min: int,
    ) -> ValidationResult:
        """WARNING if the GDS projection has fewer nodes than expected_min."""
        name = "check_gds_node_count"
        query = (
            "CALL gds.graph.list($graph_name) YIELD nodeCount "
            "RETURN nodeCount"
        )
        try:
            records = self._client.query_many(query, {"graph_name": graph_name})
            node_count = records[0]["nodeCount"] if records else 0
        except Exception as exc:
            return self._fail(name, graph_name, ValidationSeverity.ERROR,
                              f"GDS query failed while checking node count: {exc}",
                              graph_name=graph_name)
        if node_count >= expected_min:
            return self._pass(name, graph_name,
                              f"GDS projection has {node_count} nodes (expected >= {expected_min})",
                              node_count=node_count)
        return self._warn(name, graph_name,
                          f"GDS projection has {node_count} nodes; "
                          f"expected >= {expected_min} — projection filter may be too restrictive",
                          node_count=node_count, expected_min=expected_min)

    def check_gds_relationship_count(
        self, graph_name: str, expected_min: int,
    ) -> ValidationResult:
        """WARNING if the GDS projection has fewer relationships than expected_min."""
        name = "check_gds_relationship_count"
        query = (
            "CALL gds.graph.list($graph_name) YIELD relationshipCount "
            "RETURN relationshipCount"
        )
        try:
            records = self._client.query_many(query, {"graph_name": graph_name})
            rel_count = records[0]["relationshipCount"] if records else 0
        except Exception as exc:
            return self._fail(name, graph_name, ValidationSeverity.ERROR,
                              f"GDS query failed while checking relationship count: {exc}",
                              graph_name=graph_name)
        if rel_count >= expected_min:
            return self._pass(name, graph_name,
                              f"GDS projection has {rel_count} relationships "
                              f"(expected >= {expected_min})",
                              rel_count=rel_count)
        return self._warn(name, graph_name,
                          f"GDS projection has {rel_count} relationships; "
                          f"expected >= {expected_min}",
                          rel_count=rel_count, expected_min=expected_min)

    # ── Leiden output checks ───────────────────────────────────────────────────

    def check_tribe_ids_assigned(
        self,
        label: str = USER,
        property_name: str = DEFAULT_LEIDEN_WRITE_PROPERTY,
    ) -> ValidationResult:
        """WARNING if more than 10% of User nodes have no tribe_id after Leiden has run."""
        name = "check_tribe_ids_assigned"
        query = (
            f"MATCH (n:{label}) "
            f"RETURN count(n) AS total, count(n.{property_name}) AS assigned"
        )
        try:
            records = self._client.query_many(query)
            row = records[0] if records else {"total": 0, "assigned": 0}
            total = row["total"]
            assigned = row["assigned"]
        except Exception as exc:
            return self._fail(name, label, ValidationSeverity.ERROR,
                              f"Query failed while checking tribe assignment: {exc}",
                              label=label, property_name=property_name)
        if total == 0:
            return self._pass(name, label, f"No {label} nodes to check")

        unassigned_rate = (total - assigned) / total
        if unassigned_rate <= 0.10:
            return self._pass(name, label,
                              f"{assigned}/{total} {label} nodes have {property_name} assigned",
                              unassigned_rate=round(unassigned_rate, 4))
        return self._warn(name, label,
                          f"{unassigned_rate:.1%} of {label} nodes lack {property_name}",
                          total=total, assigned=assigned,
                          unassigned_rate=round(unassigned_rate, 4))

    def check_tribe_size_distribution(self) -> ValidationResult:
        """WARNING if singleton tribes (size 1) exceed 10% of all tribes."""
        name = "check_tribe_size_distribution"
        query = (
            f"MATCH (n:{USER}) WHERE n.{DEFAULT_LEIDEN_WRITE_PROPERTY} IS NOT NULL "
            f"WITH n.{DEFAULT_LEIDEN_WRITE_PROPERTY} AS tribe_id, count(*) AS size "
            "RETURN count(*) AS total_tribes, "
            "sum(CASE WHEN size = 1 THEN 1 ELSE 0 END) AS singleton_tribes"
        )
        try:
            records = self._client.query_many(query)
            row = records[0] if records else {"total_tribes": 0, "singleton_tribes": 0}
            total_tribes = row["total_tribes"]
            singleton_tribes = row["singleton_tribes"]
        except Exception as exc:
            return self._fail(name, USER, ValidationSeverity.ERROR,
                              f"Query failed while checking tribe size distribution: {exc}")
        if total_tribes == 0:
            return self._pass(name, USER, "No tribes found to check")

        singleton_rate = singleton_tribes / total_tribes
        if singleton_rate <= 0.10:
            return self._pass(name, USER,
                              f"Singleton tribe rate {singleton_rate:.1%} is acceptable",
                              total_tribes=total_tribes,
                              singleton_tribes=singleton_tribes)
        return self._warn(name, USER,
                          f"Singleton tribe rate {singleton_rate:.1%} exceeds 10%; "
                          "Leiden resolution parameter may need tuning",
                          total_tribes=total_tribes,
                          singleton_tribes=singleton_tribes,
                          singleton_rate=round(singleton_rate, 4))

    # ── PageRank output checks ─────────────────────────────────────────────────

    def check_pagerank_scores_present(self, label: str = USER) -> ValidationResult:
        """WARNING if more than 10% of User nodes have no pagerank_score."""
        name = "check_pagerank_scores_present"
        prop = DEFAULT_PAGERANK_WRITE_PROPERTY
        query = (
            f"MATCH (n:{label}) "
            f"RETURN count(n) AS total, count(n.{prop}) AS scored"
        )
        try:
            records = self._client.query_many(query)
            row = records[0] if records else {"total": 0, "scored": 0}
            total = row["total"]
            scored = row["scored"]
        except Exception as exc:
            return self._fail(name, label, ValidationSeverity.ERROR,
                              f"Query failed while checking pagerank scores: {exc}",
                              label=label)
        if total == 0:
            return self._pass(name, label, f"No {label} nodes to check")

        unscored_rate = (total - scored) / total
        if unscored_rate <= 0.10:
            return self._pass(name, label,
                              f"{scored}/{total} {label} nodes have {prop}",
                              unscored_rate=round(unscored_rate, 4))
        return self._warn(name, label,
                          f"{unscored_rate:.1%} of {label} nodes lack {prop}",
                          total=total, scored=scored,
                          unscored_rate=round(unscored_rate, 4))

    # ── Weight / inference distribution checks ────────────────────────────────

    def check_activity_weight_distribution(self, rel_type: str) -> ValidationResult:
        """INFO: min/max/mean/p50/p95 of activity_weight across all rels of the given type."""
        name = "check_activity_weight_distribution"
        prop = DEFAULT_MEMBERSHIP_ACTIVITY_WEIGHT_PROPERTY
        query = (
            f"MATCH ()-[r:{rel_type}]->() WHERE r.{prop} IS NOT NULL "
            f"WITH collect(r.{prop}) AS weights "
            "RETURN "
            "min(weights[-1]) AS min_w, max(weights[0]) AS max_w, "
            "reduce(s = 0.0, w IN weights | s + w) / size(weights) AS mean_w, "
            "size(weights) AS sample_count"
        )
        try:
            records = self._client.query_many(query)
            row = records[0] if records else {}
        except Exception as exc:
            return self._fail(name, rel_type, ValidationSeverity.ERROR,
                              f"Query failed while computing weight distribution: {exc}",
                              rel_type=rel_type)
        return ValidationResult(
            check_name=name,
            passed=True,
            severity=ValidationSeverity.INFO,
            source=rel_type,
            message=f"activity_weight distribution for {rel_type}",
            details={
                "rel_type": rel_type,
                "property": prop,
                "min": row.get("min_w"),
                "max": row.get("max_w"),
                "mean": row.get("mean_w"),
                "sample_count": row.get("sample_count", 0),
            },
            run_id=self._run_id,
        )

    def check_inference_confidence_scores(
        self, label: str = PERSONA_STATE,
    ) -> ValidationResult:
        """WARNING if more than 20% of PersonaState nodes have confidence below configured min."""
        name = "check_inference_confidence_scores"
        try:
            settings = get_settings()
            min_confidence: float = getattr(
                getattr(settings, "inference", None), "min_confidence_score", 0.5
            )
        except Exception:
            min_confidence = 0.5

        query = (
            f"MATCH (n:{label}) WHERE n.confidence_score IS NOT NULL "
            "RETURN count(n) AS total, "
            f"sum(CASE WHEN n.confidence_score < $min_confidence THEN 1 ELSE 0 END) AS below_min"
        )
        try:
            records = self._client.query_many(query, {"min_confidence": min_confidence})
            row = records[0] if records else {"total": 0, "below_min": 0}
            total = row["total"]
            below_min = row["below_min"]
        except Exception as exc:
            return self._fail(name, label, ValidationSeverity.ERROR,
                              f"Query failed while checking confidence scores: {exc}",
                              label=label)
        if total == 0:
            return self._pass(name, label,
                              f"No {label} nodes with confidence_score found")

        low_rate = below_min / total
        if low_rate <= 0.20:
            return self._pass(name, label,
                              f"Low-confidence rate {low_rate:.1%} is acceptable",
                              total=total, below_min=below_min,
                              min_confidence=min_confidence)
        return self._warn(name, label,
                          f"{low_rate:.1%} of {label} nodes have confidence < {min_confidence}",
                          total=total, below_min=below_min,
                          low_rate=round(low_rate, 4),
                          min_confidence=min_confidence)