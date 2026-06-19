"""
MySQL warehouse client for Project Pulse Knowledge Graph.

Purpose:
- provide a shared warehouse access layer for extractors
- centralize connection management and query execution
- expose stable, driver-agnostic query methods
- return predictable mapping/dict rows
- standardize logging and error handling

This module must not contain:
- source-specific SQL
- extractor logic
- schema mappings
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from time import perf_counter
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection, Engine, Result
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import MySQLSettings, get_settings
from app.core.exceptions import WarehouseConnectionError
from app.core.logging import ProjectPulseLoggerAdapter, get_logger, log_event
from app.core.security import mask_secret

SQLParams = Mapping[str, Any] | None
RowMapping = dict[str, Any]


class MySQLClient:
    """
    Shared warehouse query client.

    This client owns:
    - lazy engine creation
    - connection lifecycle
    - query execution primitives
    - health checks
    """

    def __init__(
        self,
        settings: MySQLSettings | None = None,
        *,
        logger: ProjectPulseLoggerAdapter | None = None,
    ) -> None:
        self._settings = settings or get_settings().mysql
        self._logger = logger or get_logger(__name__)
        self._engine: Engine | None = None

    @property
    def settings(self) -> MySQLSettings:
        """Return the bound MySQL settings."""
        return self._settings

    @property
    def logger(self) -> ProjectPulseLoggerAdapter:
        """Return the structured logger."""
        return self._logger

    @property
    def engine(self) -> Engine:
        """
        Return the SQLAlchemy engine, creating it lazily on first access.
        """
        if self._engine is None:
            self._engine = self._build_engine()
        return self._engine

    @classmethod
    def from_settings(
        cls,
        settings: MySQLSettings,
        *,
        logger: ProjectPulseLoggerAdapter | None = None,
    ) -> MySQLClient:
        """
        Construct a client from explicit settings.
        """
        return cls(settings=settings, logger=logger)

    def _build_engine(self) -> Engine:
        """
        Build a SQLAlchemy engine from MySQL settings.
        """
        try:
            engine = create_engine(
                self._build_sqlalchemy_url(),
                pool_pre_ping=True,
                pool_size=self._settings.pool_size,
                max_overflow=self._settings.max_overflow,
                pool_recycle=3600,
                connect_args={"connect_timeout": self._settings.connect_timeout},
                future=True,
            )

            log_event(
                self._logger,
                event_name="mysql_engine_created",
                message="MySQL engine created",
                host=self._settings.host,
                port=self._settings.port,
                database=self._settings.db,
                user=self._settings.user,
                password=mask_secret(self._settings.password),
                pool_size=self._settings.pool_size,
                max_overflow=self._settings.max_overflow,
                connect_timeout=self._settings.connect_timeout,
            )
            return engine
        except Exception as exc:  # noqa: BLE001
            raise WarehouseConnectionError(
                "Failed to create MySQL engine",
                host=self._settings.host,
                port=self._settings.port,
                database=self._settings.db,
                error_type=type(exc).__name__,
            ) from exc

    def _build_sqlalchemy_url(self) -> str:
        """
        Build the SQLAlchemy MySQL connection URL.

        Assumes the project uses the PyMySQL dialect:
        mysql+pymysql://user:password@host:port/db
        """
        user = self._settings.user
        password = self._settings.password
        host = self._settings.host
        port = self._settings.port
        database = self._settings.db
        return f"mysql+pymysql://{user}:{password}@{host}:{port}/{database}"

    @contextmanager
    def connect(self) -> Iterator[Connection]:
        """
        Acquire a connection and ensure it is closed afterward.
        """
        started = perf_counter()
        connection: Connection | None = None

        try:
            connection = self.engine.connect()
            log_event(
                self._logger,
                event_name="mysql_connection_opened",
                message="MySQL connection opened",
                host=self._settings.host,
                database=self._settings.db,
            )
            yield connection
        except SQLAlchemyError as exc:
            raise WarehouseConnectionError(
                "Failed to acquire MySQL connection",
                host=self._settings.host,
                port=self._settings.port,
                database=self._settings.db,
                error_type=type(exc).__name__,
            ) from exc
        finally:
            if connection is not None:
                connection.close()
                log_event(
                    self._logger,
                    event_name="mysql_connection_closed",
                    message="MySQL connection closed",
                    host=self._settings.host,
                    database=self._settings.db,
                    duration_ms=int((perf_counter() - started) * 1000),
                )

    def close(self) -> None:
        """
        Dispose the SQLAlchemy engine if it has been created.
        """
        if self._engine is not None:
            self._engine.dispose()
            self._engine = None
            log_event(
                self._logger,
                event_name="mysql_engine_disposed",
                message="MySQL engine disposed",
                host=self._settings.host,
                database=self._settings.db,
            )

    def ping(self) -> bool:
        """
        Check basic connectivity to the warehouse.
        """
        try:
            row = self.fetch_one("SELECT 1 AS ok")
            return bool(row and row.get("ok") == 1)
        except WarehouseConnectionError:
            return False

    def check_health(self) -> dict[str, Any]:
        """
        Return a structured health check result.
        """
        healthy = self.ping()
        return {
            "healthy": healthy,
            "host": self._settings.host,
            "port": self._settings.port,
            "database": self._settings.db,
        }

    def fetch_all(
        self,
        query: str,
        params: SQLParams = None,
    ) -> list[RowMapping]:
        """
        Execute a query and return all rows as dictionaries.
        """
        started = perf_counter()
        try:
            with self.connect() as connection:
                result = self._execute(connection, query, params)
                rows = [dict(row) for row in result.mappings().all()]

            log_event(
                self._logger,
                event_name="mysql_fetch_all_finished",
                message="MySQL fetch_all completed",
                row_count=len(rows),
                duration_ms=int((perf_counter() - started) * 1000),
            )
            return rows
        except SQLAlchemyError as exc:
            raise self._query_error("Failed to fetch rows from MySQL", exc, query) from exc

    def fetch_one(
        self,
        query: str,
        params: SQLParams = None,
    ) -> RowMapping | None:
        """
        Execute a query and return the first row as a dictionary, or None.
        """
        started = perf_counter()
        try:
            with self.connect() as connection:
                result = self._execute(connection, query, params)
                row = result.mappings().first()
                payload = dict(row) if row is not None else None

            log_event(
                self._logger,
                event_name="mysql_fetch_one_finished",
                message="MySQL fetch_one completed",
                found=payload is not None,
                duration_ms=int((perf_counter() - started) * 1000),
            )
            return payload
        except SQLAlchemyError as exc:
            raise self._query_error("Failed to fetch row from MySQL", exc, query) from exc

    def stream(
        self,
        query: str,
        params: SQLParams = None,
        *,
        chunk_size: int = 1000,
    ) -> Iterator[list[RowMapping]]:
        """
        Execute a query and stream results in chunks as lists of dictionaries.

        This keeps the underlying connection open for the lifetime of iteration.
        """
        if chunk_size <= 0:
            raise WarehouseConnectionError(
                "chunk_size must be positive",
                chunk_size=chunk_size,
            )

        started = perf_counter()
        total_rows = 0

        try:
            with self.connect() as connection:
                result = self._execute(connection, query, params)

                while True:
                    batch = result.mappings().fetchmany(chunk_size)
                    if not batch:
                        break

                    rows = [dict(row) for row in batch]
                    total_rows += len(rows)

                    log_event(
                        self._logger,
                        event_name="mysql_stream_chunk_yielded",
                        message="MySQL stream yielded chunk",
                        chunk_size=len(rows),
                        total_rows=total_rows,
                    )
                    yield rows

            log_event(
                self._logger,
                event_name="mysql_stream_finished",
                message="MySQL stream completed",
                total_rows=total_rows,
                duration_ms=int((perf_counter() - started) * 1000),
            )
        except SQLAlchemyError as exc:
            raise self._query_error("Failed to stream rows from MySQL", exc, query) from exc

    def execute(
        self,
        query: str,
        params: SQLParams = None,
    ) -> int:
        """
        Execute a non-select statement and return affected row count.
        """
        started = perf_counter()
        try:
            with self.engine.begin() as connection:
                result = self._execute(connection, query, params)
                rowcount = result.rowcount if result.rowcount is not None else 0

            log_event(
                self._logger,
                event_name="mysql_execute_finished",
                message="MySQL execute completed",
                row_count=rowcount,
                duration_ms=int((perf_counter() - started) * 1000),
            )
            return rowcount
        except SQLAlchemyError as exc:
            raise self._query_error("Failed to execute MySQL statement", exc, query) from exc

    def execute_many(
        self,
        query: str,
        rows: Sequence[Mapping[str, Any]],
    ) -> int:
        """
        Execute a statement against multiple parameter rows and return affected count.
        """
        started = perf_counter()
        try:
            with self.engine.begin() as connection:
                result = connection.execute(text(query), list(rows))
                rowcount = result.rowcount if result.rowcount is not None else 0

            log_event(
                self._logger,
                event_name="mysql_execute_many_finished",
                message="MySQL execute_many completed",
                batch_size=len(rows),
                row_count=rowcount,
                duration_ms=int((perf_counter() - started) * 1000),
            )
            return rowcount
        except SQLAlchemyError as exc:
            raise self._query_error(
                "Failed to execute many MySQL statements",
                exc,
                query,
            ) from exc

    def _execute(
        self,
        connection: Connection,
        query: str,
        params: SQLParams = None,
    ) -> Result[Any]:
        """
        Execute a parameterized SQL statement through an open connection.
        """
        started = perf_counter()

        log_event(
            self._logger,
            event_name="mysql_query_started",
            message="MySQL query started",
            has_params=bool(params),
        )

        result = connection.execute(text(query), params or {})

        log_event(
            self._logger,
            event_name="mysql_query_finished",
            message="MySQL query finished",
            duration_ms=int((perf_counter() - started) * 1000),
        )
        return result

    def _query_error(
        self,
        message: str,
        exc: Exception,
        query: str,
    ) -> WarehouseConnectionError:
        """
        Build a typed warehouse exception for query failures.
        """
        return WarehouseConnectionError(
            message,
            host=self._settings.host,
            port=self._settings.port,
            database=self._settings.db,
            error_type=type(exc).__name__,
            query_preview=self._query_preview(query),
        )

    @staticmethod
    def _query_preview(query: str, max_length: int = 160) -> str:
        """
        Return a short single-line preview of a query for logs/errors.
        """
        compact = " ".join(query.strip().split())
        if len(compact) <= max_length:
            return compact
        return compact[: max_length - 3] + "..."


# A few practical notes:

# This assumes your project dependencies include SQLAlchemy and PyMySQL.

# It uses get_settings().mysql, so it fits your Stage 2 config layer.

# It intentionally keeps SQL generic and does not know anything about extractors or schemas.

# fetch_all, fetch_one, and stream return dictionaries, which is a good fit for later typed row mapping.
