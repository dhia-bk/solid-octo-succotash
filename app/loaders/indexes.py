"""
Pre-flight index verification for the Neo4j graph.

Called once at pipeline startup. Warnings only — missing indexes degrade
performance but do not break correctness.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.logging import get_logger, log_event
from app.db.neo4j_client import Neo4jClient
from app.schemas.graph.constraints import get_all_indexes


@dataclass(frozen=True)
class IndexCheckResult:
    """
    Result of a single index verification check.

    Attributes:
        label:        Graph node label.
        property_name: Property indexed.
        present:      True if the index exists in Neo4j.
        index_name:   Neo4j index name if found, else None.
    """

    label: str
    property_name: str
    present: bool
    index_name: str | None


# SHOW INDEXES query for Neo4j 5.x
_SHOW_INDEXES_QUERY = "SHOW INDEXES YIELD name, labelsOrTypes, properties"


class IndexVerifier:
    """
    Verifies that performance-critical Neo4j indexes exist before data loading.

    All results are WARNING severity — missing indexes degrade performance
    but do not block correctness.
    """

    def __init__(self, neo4j_client: Neo4jClient) -> None:
        self._client = neo4j_client
        self._logger = get_logger(__name__)

    def verify_all(self) -> list[IndexCheckResult]:
        """
        Verify all expected indexes declared in the schema module.

        Returns a list of results. All are warnings-only — does not raise.
        """
        declared = get_all_indexes()
        results: list[IndexCheckResult] = []

        for index in declared:
            result = self.verify_index(
                label=index.label,
                property_name=index.property,
            )
            results.append(result)

        missing = [r for r in results if not r.present]
        if missing:
            missing_desc = [f"{r.label}.{r.property_name}" for r in missing]
            log_event(
                self._logger,
                event_name="indexes_missing_warning",
                message=(
                    "Performance warning: some expected Neo4j indexes are missing. "
                    "Run migrations/neo4j/002_indexes.cypher for optimal query performance."
                ),
                missing_indexes=missing_desc,
                missing_count=len(missing),
            )
        else:
            log_event(
                self._logger,
                event_name="all_indexes_present",
                message="All expected indexes verified",
                count=len(results),
            )

        return results

    def verify_index(
        self,
        label: str,
        property_name: str,
    ) -> IndexCheckResult:
        """
        Query Neo4j schema to confirm a specific index exists.

        Matches on label and property name.
        """
        records = self._client.fetch_all(_SHOW_INDEXES_QUERY)

        for record in records:
            rec_labels = record.get("labelsOrTypes") or []
            rec_props = record.get("properties") or []
            rec_name = record.get("name")

            if label in rec_labels and property_name in rec_props:
                return IndexCheckResult(
                    label=label,
                    property_name=property_name,
                    present=True,
                    index_name=str(rec_name) if rec_name else None,
                )

        return IndexCheckResult(
            label=label,
            property_name=property_name,
            present=False,
            index_name=None,
        )
