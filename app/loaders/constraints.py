"""
Pre-flight constraint verification for the Neo4j graph.

Called once at pipeline startup before any loaders run. Raises
ConfigurationError if any required constraint is missing.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.exceptions import ConfigurationError
from app.core.logging import get_logger, log_event
from app.db.neo4j_client import Neo4jClient
from app.schemas.graph.constraints import get_all_constraints


@dataclass(frozen=True)
class ConstraintCheckResult:
    """
    Result of a single constraint verification check.

    Attributes:
        label:           Graph node label.
        property_name:   Property constrained.
        constraint_type: Constraint kind (e.g. "UNIQUE").
        present:         True if the constraint exists in Neo4j.
        constraint_name: Neo4j constraint name if found, else None.
    """

    label: str
    property_name: str
    constraint_type: str
    present: bool
    constraint_name: str | None


# SHOW CONSTRAINTS query for Neo4j 5.x
_SHOW_CONSTRAINTS_QUERY = (
    "SHOW CONSTRAINTS YIELD name, type, labelsOrTypes, properties"
)


class ConstraintVerifier:
    """
    Verifies that all required Neo4j constraints exist before data loading.

    Uses SHOW CONSTRAINTS to query the live schema.
    """

    def __init__(self, neo4j_client: Neo4jClient) -> None:
        self._client = neo4j_client
        self._logger = get_logger(__name__)

    def verify_all(self) -> list[ConstraintCheckResult]:
        """
        Verify every constraint declared in CONSTRAINT_DECLARATIONS.

        Returns a list of results; does not raise on individual failures.
        Use assert_all_constraints_present() to raise on any missing constraint.
        """
        declared = get_all_constraints()
        results: list[ConstraintCheckResult] = []

        for constraint in declared:
            result = self.verify_constraint(
                label=constraint.label,
                property_name=constraint.property,
                constraint_type=constraint.constraint_type,
            )
            results.append(result)

        missing = [r for r in results if not r.present]
        log_event(
            self._logger,
            event_name="constraint_verification_finished",
            message="Constraint verification completed",
            total=len(results),
            present=len(results) - len(missing),
            missing=len(missing),
        )
        return results

    def verify_constraint(
        self,
        label: str,
        property_name: str,
        constraint_type: str = "UNIQUENESS",
    ) -> ConstraintCheckResult:
        """
        Query Neo4j schema to confirm a specific constraint exists.

        Matches on label, property name, and constraint type.
        Neo4j 5.x SHOW CONSTRAINTS returns type as "UNIQUENESS" for UNIQUE constraints.
        """
        # normalize caller-supplied "UNIQUE" → "UNIQUENESS"
        normalized_type = "UNIQUENESS" if constraint_type.upper() == "UNIQUE" else constraint_type.upper()

        records = self._client.fetch_all(_SHOW_CONSTRAINTS_QUERY)

        for record in records:
            rec_type = str(record.get("type", "")).upper()
            rec_labels = record.get("labelsOrTypes") or []
            rec_props = record.get("properties") or []
            rec_name = record.get("name")

            if (
                rec_type == normalized_type
                and label in rec_labels
                and property_name in rec_props
            ):
                return ConstraintCheckResult(
                    label=label,
                    property_name=property_name,
                    constraint_type=constraint_type,
                    present=True,
                    constraint_name=str(rec_name) if rec_name else None,
                )

        return ConstraintCheckResult(
            label=label,
            property_name=property_name,
            constraint_type=constraint_type,
            present=False,
            constraint_name=None,
        )

    def assert_all_constraints_present(self) -> None:
        """
        Verify all constraints and raise ConfigurationError if any are missing.

        Call this at pipeline startup before any loader runs.

        Raises:
            ConfigurationError: If one or more required constraints are absent.
        """
        results = self.verify_all()
        missing = [r for r in results if not r.present]

        if missing:
            missing_desc = [
                f"{r.label}.{r.property_name} ({r.constraint_type})" for r in missing
            ]
            raise ConfigurationError(
                "Required Neo4j constraints are missing. "
                "Run migrations/neo4j/001_constraints.cypher before loading data.",
                missing_constraints=missing_desc,
                missing_count=len(missing),
            )

        log_event(
            self._logger,
            event_name="all_constraints_present",
            message="All required constraints verified",
            count=len(results),
        )
