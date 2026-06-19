"""
Base loader abstractions and shared write primitives for the loader layer.

Design rules:
- No loader imports from transformers, extractors, or pipelines.
- All writes are MERGE — idempotency is mandatory.
- PII fields must never appear in any Cypher parameter dict.
- None values are stripped from property dicts before Neo4j execution.
- Write-once properties use ON CREATE SET only (enforced in merge_queries).
- All failures are logged and counted; nothing is swallowed silently.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from time import perf_counter
from typing import Any

from app.contracts.graph_records import GraphWriteBatch
from app.core.logging import get_logger, log_event
from app.db.neo4j_client import Neo4jClient
from app.schemas.graph.properties import PII_PROPERTY_NAMES


@dataclass
class LoadResult:
    """
    Result record returned by every loader after a write operation.

    Attributes:
        source_name:               Logical source/table that was loaded.
        run_id:                    Pipeline run ID for this load.
        nodes_written:             Node records successfully written to the graph.
        nodes_skipped:             Node records skipped (missing query, dry-run, etc.).
        relationships_written:     Relationship records successfully written.
        relationships_skipped:     Relationship records skipped.
        errors:                    List of error messages from failed writes.
        duration_seconds:          Wall-clock duration of the load operation.
        batch_count:               Number of write batches executed.
    """

    source_name: str
    run_id: str
    nodes_written: int = 0
    nodes_skipped: int = 0
    relationships_written: int = 0
    relationships_skipped: int = 0
    errors: list[str] = field(default_factory=list)
    duration_seconds: float = 0.0
    batch_count: int = 0

    def succeeded(self) -> bool:
        """Return True if the load completed without errors."""
        return len(self.errors) == 0

    def total_written(self) -> int:
        """Return total nodes and relationships written."""
        return self.nodes_written + self.relationships_written


class BaseLoader(ABC):
    """
    Abstract base for all loaders.

    Provides shared write primitives and enforces the loader contract.
    """

    def __init__(
        self,
        neo4j_client: Neo4jClient,
        run_id: str,
        dry_run: bool = False,
    ) -> None:
        self._client = neo4j_client
        self._run_id = run_id
        self._dry_run = dry_run
        self._logger = get_logger(__name__, run_id=run_id)

    @abstractmethod
    def load(self, batch: GraphWriteBatch) -> LoadResult:
        """
        Load a GraphWriteBatch into Neo4j.

        Must validate the batch before writing.
        Must return a LoadResult capturing what was written and any errors.
        """

    def _strip_none_values(self, properties: dict[str, Any]) -> dict[str, Any]:
        """Return a copy of properties with all None values removed."""
        return {k: v for k, v in properties.items() if v is not None}

    def _strip_pii(self, properties: dict[str, Any]) -> dict[str, Any]:
        """
        Return a copy of properties with PII fields removed.

        Raises RuntimeError if any PII field is found — PII should have been
        stripped by the transformer layer before this point.
        """
        pii_found = sorted(k for k in properties if k in PII_PROPERTY_NAMES)
        if pii_found:
            raise RuntimeError(
                f"PII fields reached loader layer: {pii_found}. "
                "Transformer must strip PII before producing NodeRecord/RelationshipRecord."
            )
        return properties

    def _execute(self, query: str, parameters: dict[str, Any]) -> dict[str, Any]:
        """
        Execute a single Cypher statement. No-op in dry_run mode.
        """
        if self._dry_run:
            log_event(
                self._logger,
                event_name="loader_dry_run_skip",
                message="Dry-run: skipped single Cypher execute",
                run_id=self._run_id,
            )
            return {"records": [], "summary": {"counters": {}}}

        return self._client.run_write(query, parameters)

    def _execute_batch(self, query: str, rows: list[dict[str, Any]]) -> int:
        """
        Execute a Cypher statement with UNWIND over a list of parameter dicts.

        Returns the number of rows processed. No-op in dry_run mode.
        """
        if not rows:
            return 0

        if self._dry_run:
            log_event(
                self._logger,
                event_name="loader_dry_run_skip",
                message="Dry-run: skipped batch Cypher execute",
                run_id=self._run_id,
                row_count=len(rows),
            )
            return len(rows)

        self._client.run_many(query, rows, rows_param_name="rows")
        return len(rows)

    @staticmethod
    def _elapsed(started: float) -> float:
        """Return wall-clock seconds since started."""
        return perf_counter() - started
