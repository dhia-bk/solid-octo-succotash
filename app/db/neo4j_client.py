"""
Neo4j graph client for Project Pulse Knowledge Graph.

Purpose:
- provide a shared graph execution layer for Cypher reads and writes
- centralize Neo4j driver and session lifecycle
- expose stable query execution methods for loaders, analytics, and services
- return predictable mapping/dict records
- standardize logging and error handling

This module must not contain:
- merge query logic
- ontology-specific Cypher
- loader domain behavior
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from time import perf_counter
from typing import Any

from neo4j import Driver, GraphDatabase, ManagedTransaction, Result, Session
from neo4j.exceptions import Neo4jError

from app.core.config import Neo4jSettings, get_settings
from app.core.exceptions import GraphConnectionError
from app.core.logging import ProjectPulseLoggerAdapter, get_logger, log_event
from app.core.security import mask_secret

CypherParams = Mapping[str, Any] | None
GraphRecord = dict[str, Any]
GraphSummary = dict[str, Any]


class Neo4jClient:
    """
    Shared Neo4j graph execution client.

    This client owns:
    - lazy driver creation
    - session lifecycle
    - query execution primitives
    - connectivity verification
    - cleanup
    """

    def __init__(
        self,
        settings: Neo4jSettings | None = None,
        *,
        logger: ProjectPulseLoggerAdapter | None = None,
    ) -> None:
        self._settings = settings or get_settings().neo4j
        self._logger = logger or get_logger(__name__)
        self._driver: Driver | None = None

    @property
    def settings(self) -> Neo4jSettings:
        """Return the bound Neo4j settings."""
        return self._settings

    @property
    def logger(self) -> ProjectPulseLoggerAdapter:
        """Return the structured logger."""
        return self._logger

    @property
    def driver(self) -> Driver:
        """
        Return the Neo4j driver, creating it lazily on first access.
        """
        if self._driver is None:
            self._driver = self._build_driver()
        return self._driver

    @classmethod
    def from_settings(
        cls,
        settings: Neo4jSettings,
        *,
        logger: ProjectPulseLoggerAdapter | None = None,
    ) -> Neo4jClient:
        """
        Construct a client from explicit settings.
        """
        return cls(settings=settings, logger=logger)

    def _build_driver(self) -> Driver:
        """
        Build a Neo4j driver from configured settings.
        """
        try:
            driver = GraphDatabase.driver(
                self._settings.uri,
                auth=(self._settings.user, self._settings.password),
            )

            log_event(
                self._logger,
                event_name="neo4j_driver_created",
                message="Neo4j driver created",
                uri=self._settings.uri,
                user=self._settings.user,
                password=mask_secret(self._settings.password),
                database=self._settings.database,
            )
            return driver
        except Exception as exc:  # noqa: BLE001
            raise GraphConnectionError(
                "Failed to create Neo4j driver",
                uri=self._settings.uri,
                database=self._settings.database,
                error_type=type(exc).__name__,
            ) from exc

    @contextmanager
    def session(self) -> Iterator[Session]:
        """
        Acquire a Neo4j session and ensure it is closed afterward.
        """
        started = perf_counter()
        session: Session | None = None

        try:
            session = self.driver.session(database=self._settings.database)
            log_event(
                self._logger,
                event_name="neo4j_session_opened",
                message="Neo4j session opened",
                database=self._settings.database,
            )
            yield session
        except Neo4jError as exc:
            raise GraphConnectionError(
                "Failed to acquire Neo4j session",
                uri=self._settings.uri,
                database=self._settings.database,
                error_type=type(exc).__name__,
            ) from exc
        finally:
            if session is not None:
                session.close()
                log_event(
                    self._logger,
                    event_name="neo4j_session_closed",
                    message="Neo4j session closed",
                    database=self._settings.database,
                    duration_ms=int((perf_counter() - started) * 1000),
                )

    def close(self) -> None:
        """
        Close the Neo4j driver if it has been created.
        """
        if self._driver is not None:
            self._driver.close()
            self._driver = None
            log_event(
                self._logger,
                event_name="neo4j_driver_closed",
                message="Neo4j driver closed",
                database=self._settings.database,
            )

    def verify_connectivity(self) -> None:
        """
        Verify driver connectivity to the target Neo4j database.
        """
        try:
            self.driver.verify_connectivity()
            log_event(
                self._logger,
                event_name="neo4j_connectivity_verified",
                message="Neo4j connectivity verified",
                database=self._settings.database,
            )
        except Exception as exc:  # noqa: BLE001
            raise GraphConnectionError(
                "Failed to verify Neo4j connectivity",
                uri=self._settings.uri,
                database=self._settings.database,
                error_type=type(exc).__name__,
            ) from exc

    def check_health(self) -> dict[str, Any]:
        """
        Return a structured health result for Neo4j.
        """
        try:
            self.verify_connectivity()
            healthy = True
        except GraphConnectionError:
            healthy = False

        return {
            "healthy": healthy,
            "uri": self._settings.uri,
            "database": self._settings.database,
        }

    def fetch_all(
        self,
        cypher: str,
        params: CypherParams = None,
    ) -> list[GraphRecord]:
        """
        Execute a read query and return all records as dictionaries.
        """
        payload = self.run_read(cypher, params)
        return payload["records"]

    def fetch_one(
        self,
        cypher: str,
        params: CypherParams = None,
    ) -> GraphRecord | None:
        """
        Execute a read query and return the first record as a dictionary, or None.
        """
        records = self.fetch_all(cypher, params)
        return records[0] if records else None

    def run_read(
        self,
        cypher: str,
        params: CypherParams = None,
    ) -> dict[str, Any]:
        """
        Execute a read transaction and return records plus summary metadata.
        """
        started = perf_counter()

        try:
            with self.session() as session:
                result = session.execute_read(self._run_cypher, cypher, params or {})
                payload = self._consume_result(result)

            log_event(
                self._logger,
                event_name="neo4j_read_finished",
                message="Neo4j read query completed",
                database=self._settings.database,
                row_count=len(payload["records"]),
                duration_ms=int((perf_counter() - started) * 1000),
            )
            return payload
        except Neo4jError as exc:
            raise self._query_error("Failed to execute Neo4j read query", exc, cypher) from exc

    def run_write(
        self,
        cypher: str,
        params: CypherParams = None,
    ) -> dict[str, Any]:
        """
        Execute a write transaction and return records plus summary metadata.
        """
        started = perf_counter()

        try:
            with self.session() as session:
                result = session.execute_write(self._run_cypher, cypher, params or {})
                payload = self._consume_result(result)

            log_event(
                self._logger,
                event_name="neo4j_write_finished",
                message="Neo4j write query completed",
                database=self._settings.database,
                row_count=len(payload["records"]),
                nodes_created=payload["summary"]["counters"]["nodes_created"],
                relationships_created=payload["summary"]["counters"]["relationships_created"],
                properties_set=payload["summary"]["counters"]["properties_set"],
                duration_ms=int((perf_counter() - started) * 1000),
            )
            return payload
        except Neo4jError as exc:
            raise self._query_error("Failed to execute Neo4j write query", exc, cypher) from exc

    def run_many(
        self,
        cypher: str,
        rows: Sequence[Mapping[str, Any]],
        *,
        rows_param_name: str = "rows",
    ) -> dict[str, Any]:
        """
        Execute a row-driven bulk write using UNWIND-style parameters.

        Example pattern:
            UNWIND $rows AS row
            MERGE ...
        """
        started = perf_counter()

        try:
            payload = self.run_write(cypher, {rows_param_name: list(rows)})

            log_event(
                self._logger,
                event_name="neo4j_bulk_write_finished",
                message="Neo4j bulk write completed",
                database=self._settings.database,
                batch_size=len(rows),
                nodes_created=payload["summary"]["counters"]["nodes_created"],
                relationships_created=payload["summary"]["counters"]["relationships_created"],
                duration_ms=int((perf_counter() - started) * 1000),
            )
            return payload
        except GraphConnectionError:
            raise

    @staticmethod
    def _run_cypher(
        tx: ManagedTransaction,
        cypher: str,
        params: Mapping[str, Any],
    ) -> tuple[list[dict], Any]:
        """
        Execute Cypher inside a managed transaction and consume results immediately.
        Neo4j 5.x requires results to be consumed before the transaction closes.
        """
        result = tx.run(cypher, **params)
        records = [dict(r.items()) for r in result]
        summary = result.consume()
        return records, summary

    def _consume_result(self, payload: tuple[list[dict], Any]) -> dict[str, Any]:
        """
        Convert the pre-consumed (records, summary) tuple into stable dict shape.
        """
        records, summary = payload
        return {
            "records": records,
            "summary": self._build_summary(summary),
        }

    @staticmethod
    def _build_summary(summary: Any) -> GraphSummary:
        """
        Convert a Neo4j summary into a stable dictionary shape.
        """
        counters = summary.counters

        return {
            "query_type": getattr(summary, "query_type", None),
            "database": getattr(getattr(summary, "database", None), "name", None),
            "result_available_after_ms": getattr(summary, "result_available_after", None),
            "result_consumed_after_ms": getattr(summary, "result_consumed_after", None),
            "counters": {
                "nodes_created": counters.nodes_created,
                "nodes_deleted": counters.nodes_deleted,
                "relationships_created": counters.relationships_created,
                "relationships_deleted": counters.relationships_deleted,
                "properties_set": counters.properties_set,
                "labels_added": counters.labels_added,
                "labels_removed": counters.labels_removed,
                "indexes_added": counters.indexes_added,
                "indexes_removed": counters.indexes_removed,
                "constraints_added": counters.constraints_added,
                "constraints_removed": counters.constraints_removed,
                "system_updates": counters.system_updates,
                "contains_updates": counters.contains_updates,
                "contains_system_updates": counters.contains_system_updates,
            },
        }

    def _query_error(
        self,
        message: str,
        exc: Exception,
        cypher: str,
    ) -> GraphConnectionError:
        """
        Build a typed graph exception for query failures.
        """
        return GraphConnectionError(
            message,
            uri=self._settings.uri,
            database=self._settings.database,
            error_type=type(exc).__name__,
            query_preview=self._query_preview(cypher),
        )

    @staticmethod
    def _query_preview(cypher: str, max_length: int = 160) -> str:
        """
        Return a short single-line preview of a Cypher statement for logs/errors.
        """
        compact = " ".join(cypher.strip().split())
        if len(compact) <= max_length:
            return compact
        return compact[: max_length - 3] + "..."


# A few practical notes:

# This assumes your metadata DB is also MySQL-compatible. If you later switch metadata storage to Postgres, you only need to change the connection URL builder and driver dependency, not the repository APIs.

# The transaction() method is where transaction.py actually becomes useful. This is the place where a shared commit/rollback/close pattern pays off.

# Repository modules like checkpoints.py and job_runs.py should depend on this client, not build their own engines or sessions.
