"""
Batch writer — batching, retry, and transaction management for all Neo4j writes.

NodeLoader and RelationshipLoader delegate all Cypher execution here.

Design rules:
- All writes use UNWIND $rows AS row patterns for efficient bulk execution.
- Batches are bounded by batch_size to avoid memory pressure.
- Neo4j driver handles transient errors (deadlock, timeout) via managed
  transactions. BatchWriter retries on GraphConnectionError (network/timeout).
- None values and PII fields are stripped from every row before execution.
- dry_run mode logs instead of executing; all methods still return counts.
"""

from __future__ import annotations

import time
from typing import Any

from app.contracts.graph_records import NodeRecord, RelationshipRecord
from app.core.constants import (
    DEFAULT_BATCH_SIZE,
    DEFAULT_MAX_RETRIES,
    DEFAULT_RETRY_BACKOFF_SECONDS,
)
from app.core.exceptions import BatchWriteError, GraphConnectionError
from app.core.logging import get_logger, log_event
from app.core.time import format_iso_timestamp, utc_now
from app.db.neo4j_client import Neo4jClient
from app.schemas.graph.properties import PII_PROPERTY_NAMES


class BatchWriter:
    """
    Handles batching, transaction management, and retry logic for all writes.

    All writes use UNWIND $rows AS row. Rows are chunked into batches of
    batch_size before being sent to Neo4j.
    """

    def __init__(
        self,
        neo4j_client: Neo4jClient,
        run_id: str,
        batch_size: int = DEFAULT_BATCH_SIZE,
        max_retries: int = DEFAULT_MAX_RETRIES,
        retry_backoff_seconds: int = DEFAULT_RETRY_BACKOFF_SECONDS,
        dry_run: bool = False,
    ) -> None:
        self._client = neo4j_client
        self._run_id = run_id
        self._batch_size = batch_size
        self._max_retries = max_retries
        self._retry_backoff_seconds = retry_backoff_seconds
        self._dry_run = dry_run
        self._logger = get_logger(__name__, run_id=run_id)

    def write_nodes(
        self,
        query: str,
        records: list[NodeRecord],
    ) -> tuple[int, int]:
        """
        UNWIND NodeRecords into the given MERGE query in batches.

        Returns (written_count, skipped_count).
        """
        if not records:
            return 0, 0

        rows = [self._build_node_row(r) for r in records]
        written = self._write_rows(query, rows)
        skipped = len(records) - written
        return written, max(0, skipped)

    def write_relationships(
        self,
        query: str,
        records: list[RelationshipRecord],
    ) -> tuple[int, int]:
        """
        UNWIND RelationshipRecords into the given MERGE query in batches.

        Returns (written_count, skipped_count).
        """
        if not records:
            return 0, 0

        rows = [self._build_relationship_row(r) for r in records]
        written = self._write_rows(query, rows)
        skipped = len(records) - written
        return written, max(0, skipped)

    def write_single(self, query: str, parameters: dict[str, Any]) -> None:
        """Execute a single Cypher statement with retry."""
        self._execute_with_retry(query, parameters)

    # ── Internal helpers ────────────────────────────────────────────────────

    def _write_rows(self, query: str, rows: list[dict[str, Any]]) -> int:
        """Chunk rows into batches and execute each with retry. Returns count written."""
        written = 0
        for i in range(0, len(rows), self._batch_size):
            batch = rows[i : i + self._batch_size]
            if self._dry_run:
                log_event(
                    self._logger,
                    event_name="batch_writer_dry_run",
                    message="Dry-run: skipped batch write",
                    batch_size=len(batch),
                    run_id=self._run_id,
                )
                written += len(batch)
                continue
            self._execute_with_retry(query, {"rows": batch})
            written += len(batch)
        return written

    def _execute_with_retry(
        self,
        query: str,
        parameters: dict[str, Any],
        attempt: int = 0,
    ) -> None:
        """
        Retry wrapper for transient Neo4j errors.

        Neo4j's managed transaction handles deadlock/timeout retries internally.
        This layer retries on GraphConnectionError (network interruptions).
        Raises BatchWriteError on exhausted retries or non-transient failures.
        """
        try:
            self._client.run_write(query, parameters)
        except GraphConnectionError as exc:
            if attempt >= self._max_retries:
                log_event(
                    self._logger,
                    event_name="batch_write_failed",
                    message="Batch write failed after max retries",
                    attempt=attempt,
                    max_retries=self._max_retries,
                    error=str(exc),
                    run_id=self._run_id,
                )
                raise BatchWriteError(
                    "Batch write failed after max retries",
                    attempt=attempt,
                    max_retries=self._max_retries,
                    error=str(exc),
                    run_id=self._run_id,
                ) from exc

            backoff = self._retry_backoff_seconds * (2**attempt)
            log_event(
                self._logger,
                event_name="batch_write_retrying",
                message=f"Batch write error — retrying in {backoff}s (attempt {attempt + 1})",
                attempt=attempt + 1,
                backoff_seconds=backoff,
                error=str(exc),
                run_id=self._run_id,
            )
            time.sleep(backoff)
            self._execute_with_retry(query, parameters, attempt + 1)

    def _build_node_row(self, record: NodeRecord) -> dict[str, Any]:
        """
        Convert a NodeRecord to a Cypher parameter row dict.

        Strips None values. Raises on PII fields (should never reach here).
        Adds system _meta properties.
        """
        now_iso = format_iso_timestamp(utc_now())
        props = {k: v for k, v in record.properties.items() if v is not None}

        # PII guard — should have been stripped by transformer
        pii = sorted(k for k in props if k in PII_PROPERTY_NAMES)
        if pii:
            raise BatchWriteError(
                "PII fields found in NodeRecord properties at write time",
                pii_fields=pii,
                node_id=record.node_id,
                source_name=record.source_name,
            )

        row: dict[str, Any] = {
            "id": record.node_id,
            "_source_name": record.source_name,
            "_run_id": record.pipeline_run_id,
            "_created_at": now_iso,
            "_updated_at": now_iso,
        }

        if record.weighting_version is not None:
            row["_weighting_version"] = record.weighting_version

        row.update(props)
        return row

    def _build_relationship_row(self, record: RelationshipRecord) -> dict[str, Any]:
        """
        Convert a RelationshipRecord to a Cypher parameter row dict.

        Strips None values. Raises on PII fields.
        Adds system _meta properties and start_id/end_id for MATCH clauses.
        """
        now_iso = format_iso_timestamp(utc_now())
        props = {k: v for k, v in record.properties.items() if v is not None}

        pii = sorted(k for k in props if k in PII_PROPERTY_NAMES)
        if pii:
            raise BatchWriteError(
                "PII fields found in RelationshipRecord properties at write time",
                pii_fields=pii,
                rel_type=record.rel_type,
                start_node_id=record.start_node_id,
                source_name=record.source_name,
            )

        row: dict[str, Any] = {
            "start_id": record.start_node_id,
            "end_id": record.end_node_id,
            "_source_name": record.source_name,
            "_run_id": record.pipeline_run_id,
            "_created_at": now_iso,
            "_updated_at": now_iso,
        }

        row.update(props)
        return row
