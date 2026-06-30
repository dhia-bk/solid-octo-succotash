"""
Metadata database client for Project Pulse Knowledge Graph.

Purpose:
- provide a shared metadata DB access layer for operational repositories
- centralize engine and session management
- expose stable execution helpers for repository modules
- standardize logging and error handling

This module must not contain:
- checkpoint business logic
- job run business logic
- model registry business logic
- source inventory business logic
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from time import perf_counter
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, Result
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import MetadataDBSettings, get_settings
from app.core.exceptions import MetadataDatabaseError
from app.core.logging import ProjectPulseLoggerAdapter, get_logger, log_event
from app.core.security import mask_secret
from app.db.transaction import transaction_scope

SQLParams = Mapping[str, Any] | None
RowMapping = dict[str, Any]


class SQLAlchemySessionResource:
    """
    Adapter that makes a SQLAlchemy Session compatible with transaction_scope().
    """

    def __init__(self, session: Session) -> None:
        self._session = session
        self._transaction = None

    @property
    def session(self) -> Session:
        return self._session

    def begin(self) -> None:
        self._transaction = self._session.begin()
        self._transaction.__enter__()

    def commit(self) -> None:
        self._session.commit()

    def rollback(self) -> None:
        self._session.rollback()

    def close(self) -> None:
        self._session.close()


class MetadataDBClient:
    """
    Shared metadata DB client/session factory.

    This client owns:
    - lazy engine creation
    - session factory creation
    - session lifecycle
    - execution helpers
    - health checks
    - cleanup
    """

    def __init__(
        self,
        settings: MetadataDBSettings | None = None,
        *,
        logger: ProjectPulseLoggerAdapter | None = None,
    ) -> None:
        self._settings = settings or get_settings().metadata_db
        self._logger = logger or get_logger(__name__)
        self._engine: Engine | None = None
        self._session_factory: sessionmaker[Session] | None = None

    @property
    def settings(self) -> MetadataDBSettings:
        return self._settings

    @property
    def logger(self) -> ProjectPulseLoggerAdapter:
        return self._logger

    @property
    def engine(self) -> Engine:
        if self._engine is None:
            self._engine = self._build_engine()
        return self._engine

    @property
    def session_factory(self) -> sessionmaker[Session]:
        if self._session_factory is None:
            self._session_factory = sessionmaker(
                bind=self.engine,
                autoflush=False,
                autocommit=False,
                expire_on_commit=False,
                future=True,
            )
        return self._session_factory

    @classmethod
    def from_settings(
        cls,
        settings: MetadataDBSettings,
        *,
        logger: ProjectPulseLoggerAdapter | None = None,
    ) -> MetadataDBClient:
        return cls(settings=settings, logger=logger)

    def _build_engine(self) -> Engine:
        try:
            engine = create_engine(
                self._build_sqlalchemy_url(),
                pool_pre_ping=True,
                pool_size=self._settings.pool_size,
                max_overflow=self._settings.max_overflow,
                pool_recycle=3600,
                future=True,
            )

            log_event(
                self._logger,
                event_name="metadata_engine_created",
                message="Metadata DB engine created",
                host=self._settings.host,
                port=self._settings.port,
                database=self._settings.name,
                user=self._settings.user,
                password=mask_secret(self._settings.password),
                pool_size=self._settings.pool_size,
                max_overflow=self._settings.max_overflow,
            )
            return engine
        except Exception as exc:  # noqa: BLE001
            raise MetadataDatabaseError(
                "Failed to create metadata DB engine",
                host=self._settings.host,
                port=self._settings.port,
                database=self._settings.name,
                error_type=type(exc).__name__,
            ) from exc

    def _build_sqlalchemy_url(self) -> str:
        """
        Build the SQLAlchemy connection URL for the metadata DB (PostgreSQL).
        """
        user = self._settings.user
        password = self._settings.password
        host = self._settings.host
        port = self._settings.port
        database = self._settings.name
        return f"postgresql+psycopg://{user}:{password}@{host}:{port}/{database}"

    @contextmanager
    def session(self) -> Iterator[Session]:
        started = perf_counter()
        session = self.session_factory()

        try:
            log_event(
                self._logger,
                event_name="metadata_session_opened",
                message="Metadata DB session opened",
                host=self._settings.host,
                database=self._settings.name,
            )
            yield session
        except SQLAlchemyError as exc:
            raise MetadataDatabaseError(
                "Failed during metadata DB session usage",
                host=self._settings.host,
                port=self._settings.port,
                database=self._settings.name,
                error_type=type(exc).__name__,
            ) from exc
        finally:
            session.close()
            log_event(
                self._logger,
                event_name="metadata_session_closed",
                message="Metadata DB session closed",
                host=self._settings.host,
                database=self._settings.name,
                duration_ms=int((perf_counter() - started) * 1000),
            )

    @contextmanager
    def transaction(
        self, *, transaction_name: str = "metadata_transaction", **context: Any
    ) -> Iterator[Session]:
        """
        Provide a transaction-scoped SQLAlchemy Session using the shared
        transaction abstraction from app.db.transaction.
        """
        with self.session() as session:
            resource = SQLAlchemySessionResource(session)
            with transaction_scope(
                resource,
                logger=self._logger,
                transaction_name=transaction_name,
                error_factory=self._map_transaction_error,
                database=self._settings.name,
                **context,
            ) as tx:
                yield tx.session

    def close(self) -> None:
        if self._engine is not None:
            self._engine.dispose()
            self._engine = None
            self._session_factory = None
            log_event(
                self._logger,
                event_name="metadata_engine_disposed",
                message="Metadata DB engine disposed",
                host=self._settings.host,
                database=self._settings.name,
            )

    def ping(self) -> bool:
        try:
            row = self.fetch_one("SELECT 1 AS ok")
            return bool(row and row.get("ok") == 1)
        except MetadataDatabaseError:
            return False

    def check_health(self) -> dict[str, Any]:
        healthy = self.ping()
        return {
            "healthy": healthy,
            "host": self._settings.host,
            "port": self._settings.port,
            "database": self._settings.name,
        }

    def execute(
        self,
        statement: str,
        params: SQLParams = None,
    ) -> int:
        """
        Execute a non-select statement and return affected row count.
        """
        started = perf_counter()
        try:
            with self.engine.begin() as connection:
                result = connection.execute(text(statement), params or {})
                rowcount = result.rowcount if result.rowcount is not None else 0

            log_event(
                self._logger,
                event_name="metadata_execute_finished",
                message="Metadata DB execute completed",
                row_count=rowcount,
                duration_ms=int((perf_counter() - started) * 1000),
            )
            return rowcount
        except SQLAlchemyError as exc:
            raise self._query_error(
                "Failed to execute metadata DB statement",
                exc,
                statement,
            ) from exc

    def execute_many(
        self,
        statement: str,
        rows: Sequence[Mapping[str, Any]],
    ) -> int:
        """
        Execute a statement against multiple parameter rows.
        """
        started = perf_counter()
        try:
            with self.engine.begin() as connection:
                result = connection.execute(text(statement), list(rows))
                rowcount = result.rowcount if result.rowcount is not None else 0

            log_event(
                self._logger,
                event_name="metadata_execute_many_finished",
                message="Metadata DB execute_many completed",
                batch_size=len(rows),
                row_count=rowcount,
                duration_ms=int((perf_counter() - started) * 1000),
            )
            return rowcount
        except SQLAlchemyError as exc:
            raise self._query_error(
                "Failed to execute many metadata DB statements",
                exc,
                statement,
            ) from exc

    def fetch_one(
        self,
        statement: str,
        params: SQLParams = None,
    ) -> RowMapping | None:
        """
        Execute a query and return the first row as a dictionary, or None.
        """
        started = perf_counter()
        try:
            with self.engine.connect() as connection:
                result = connection.execute(text(statement), params or {})
                row = result.mappings().first()
                payload = dict(row) if row is not None else None

            log_event(
                self._logger,
                event_name="metadata_fetch_one_finished",
                message="Metadata DB fetch_one completed",
                found=payload is not None,
                duration_ms=int((perf_counter() - started) * 1000),
            )
            return payload
        except SQLAlchemyError as exc:
            raise self._query_error(
                "Failed to fetch row from metadata DB",
                exc,
                statement,
            ) from exc

    def fetch_all(
        self,
        statement: str,
        params: SQLParams = None,
    ) -> list[RowMapping]:
        """
        Execute a query and return all rows as dictionaries.
        """
        started = perf_counter()
        try:
            with self.engine.connect() as connection:
                result = connection.execute(text(statement), params or {})
                rows = [dict(row) for row in result.mappings().all()]

            log_event(
                self._logger,
                event_name="metadata_fetch_all_finished",
                message="Metadata DB fetch_all completed",
                row_count=len(rows),
                duration_ms=int((perf_counter() - started) * 1000),
            )
            return rows
        except SQLAlchemyError as exc:
            raise self._query_error(
                "Failed to fetch rows from metadata DB",
                exc,
                statement,
            ) from exc

    def fetch_scalar(
        self,
        statement: str,
        params: SQLParams = None,
    ) -> Any:
        """
        Execute a query and return the first scalar value, or None.
        """
        started = perf_counter()
        try:
            with self.engine.connect() as connection:
                result: Result[Any] = connection.execute(text(statement), params or {})
                value = result.scalar_one_or_none()

            log_event(
                self._logger,
                event_name="metadata_fetch_scalar_finished",
                message="Metadata DB fetch_scalar completed",
                duration_ms=int((perf_counter() - started) * 1000),
            )
            return value
        except SQLAlchemyError as exc:
            raise self._query_error(
                "Failed to fetch scalar from metadata DB",
                exc,
                statement,
            ) from exc

    def _map_transaction_error(self, exc: Exception) -> MetadataDatabaseError:
        return MetadataDatabaseError(
            "Metadata DB transaction failed",
            host=self._settings.host,
            port=self._settings.port,
            database=self._settings.name,
            error_type=type(exc).__name__,
        )

    def _query_error(
        self,
        message: str,
        exc: Exception,
        statement: str,
    ) -> MetadataDatabaseError:
        return MetadataDatabaseError(
            message,
            host=self._settings.host,
            port=self._settings.port,
            database=self._settings.name,
            error_type=type(exc).__name__,
            query_preview=self._query_preview(statement),
        )

    @staticmethod
    def _query_preview(statement: str, max_length: int = 160) -> str:
        compact = " ".join(statement.strip().split())
        if len(compact) <= max_length:
            return compact
        return compact[: max_length - 3] + "..."


# A few practical notes:

# This assumes your metadata DB is also MySQL-compatible. If you later switch metadata storage to Postgres, you only need to change the connection URL builder and driver dependency, not the repository APIs.

# The transaction() method is where transaction.py actually becomes useful. This is the place where a shared commit/rollback/close pattern pays off.

# Repository modules like checkpoints.py and job_runs.py should depend on this client, not build their own engines or sessions.
