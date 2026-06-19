"""
Shared transaction abstractions for Project Pulse Knowledge Graph.

Purpose:
- standardize begin/commit/rollback/close behavior across storage layers
- provide reusable context managers for transactional work
- centralize transaction logging and error mapping
- remain database-agnostic

This module should not know anything about:
- SQL syntax
- Cypher syntax
- table names
- ontology or graph schema
- repository-specific persistence rules
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from time import perf_counter
from typing import Any, Protocol, TypeVar, runtime_checkable

from app.core.exceptions import DatabaseError, ProjectPulseError
from app.core.logging import ProjectPulseLoggerAdapter, get_logger, log_event

TTransaction = TypeVar("TTransaction", bound="TransactionResource")

_DEFAULT_LOGGER = get_logger(__name__)


@runtime_checkable
class TransactionResource(Protocol):
    """
    Protocol for a transaction-capable resource.

    Concrete implementations may wrap:
    - SQLAlchemy sessions/connections
    - Neo4j transactions/sessions
    - metadata DB sessions
    - custom unit-of-work objects

    The contract is intentionally minimal.
    """

    def begin(self) -> Any:
        """Begin a transaction."""

    def commit(self) -> Any:
        """Commit a transaction."""

    def rollback(self) -> Any:
        """Roll back a transaction."""

    def close(self) -> Any:
        """Release/close the underlying resource."""


ErrorFactory = Callable[[Exception], ProjectPulseError]


def _default_error_factory(exc: Exception) -> ProjectPulseError:
    """
    Map an unexpected transaction exception to a generic database error.
    """
    if isinstance(exc, ProjectPulseError):
        return exc

    return DatabaseError(
        "Transactional operation failed",
        error_type=type(exc).__name__,
    )


def _duration_ms(start: float) -> int:
    """
    Convert a perf_counter start time into elapsed milliseconds.
    """
    return int((perf_counter() - start) * 1000)


@contextmanager
def transaction_scope(
    resource: TTransaction,
    *,
    logger: ProjectPulseLoggerAdapter | None = None,
    transaction_name: str = "transaction",
    error_factory: ErrorFactory | None = None,
    **context: Any,
) -> Iterator[TTransaction]:
    """
    Execute work inside a managed transaction scope.

    Behavior:
    - begin the transaction
    - yield the resource
    - commit on success
    - rollback on failure
    - always close the resource

    Args:
        resource: Transaction-capable resource.
        logger: Optional structured logger.
        transaction_name: Human-readable transaction name for logs.
        error_factory: Optional exception mapper.
        **context: Structured log context.

    Yields:
        The same transaction-capable resource.

    Raises:
        ProjectPulseError: Mapped project exception.
    """
    active_logger = logger or _DEFAULT_LOGGER
    map_error = error_factory or _default_error_factory
    started = perf_counter()

    log_event(
        active_logger,
        event_name="transaction_started",
        message="Transaction started",
        transaction_name=transaction_name,
        **context,
    )

    try:
        resource.begin()
        yield resource
        resource.commit()

        log_event(
            active_logger,
            event_name="transaction_committed",
            message="Transaction committed",
            transaction_name=transaction_name,
            duration_ms=_duration_ms(started),
            **context,
        )
    except Exception as exc:  # noqa: BLE001
        rollback_error: Exception | None = None

        try:
            resource.rollback()
            log_event(
                active_logger,
                event_name="transaction_rolled_back",
                message="Transaction rolled back",
                transaction_name=transaction_name,
                duration_ms=_duration_ms(started),
                error_type=type(exc).__name__,
                **context,
            )
        except Exception as rollback_exc:  # noqa: BLE001
            rollback_error = rollback_exc
            log_event(
                active_logger,
                event_name="transaction_rollback_failed",
                level=40,
                message="Transaction rollback failed",
                transaction_name=transaction_name,
                duration_ms=_duration_ms(started),
                error_type=type(exc).__name__,
                rollback_error_type=type(rollback_exc).__name__,
                **context,
            )

        mapped_error = map_error(exc)

        if rollback_error is not None:
            raise mapped_error from rollback_error

        raise mapped_error from exc
    finally:
        try:
            resource.close()
            log_event(
                active_logger,
                event_name="transaction_closed",
                message="Transaction resource closed",
                transaction_name=transaction_name,
                duration_ms=_duration_ms(started),
                **context,
            )
        except Exception as exc:  # noqa: BLE001
            log_event(
                active_logger,
                event_name="transaction_close_failed",
                level=40,
                message="Transaction resource close failed",
                transaction_name=transaction_name,
                duration_ms=_duration_ms(started),
                error_type=type(exc).__name__,
                **context,
            )


@contextmanager
def managed_transaction(
    resource: TTransaction,
    *,
    logger: ProjectPulseLoggerAdapter | None = None,
    transaction_name: str = "transaction",
    error_factory: ErrorFactory | None = None,
    **context: Any,
) -> Iterator[TTransaction]:
    """
    Alias wrapper around transaction_scope for readability in callers.
    """
    with transaction_scope(
        resource,
        logger=logger,
        transaction_name=transaction_name,
        error_factory=error_factory,
        **context,
    ) as tx:
        yield tx


def run_in_transaction[
    TTransaction
](
    resource: TTransaction,
    operation: Callable[[TTransaction], Any],
    *,
    logger: ProjectPulseLoggerAdapter | None = None,
    transaction_name: str = "transaction",
    error_factory: ErrorFactory | None = None,
    **context: Any,
) -> Any:
    """
    Execute a callable inside a managed transaction and return its result.

    Args:
        resource: Transaction-capable resource.
        operation: Callable that receives the transaction resource.
        logger: Optional structured logger.
        transaction_name: Human-readable transaction name.
        error_factory: Optional exception mapper.
        **context: Structured log context.

    Returns:
        The operation result.
    """
    with transaction_scope(
        resource,
        logger=logger,
        transaction_name=transaction_name,
        error_factory=error_factory,
        **context,
    ) as tx:
        return operation(tx)


def retry_transaction(
    resource_factory: Callable[[], TTransaction],
    operation: Callable[[TTransaction], Any],
    *,
    attempts: int = 3,
    should_retry: Callable[[Exception], bool] | None = None,
    logger: ProjectPulseLoggerAdapter | None = None,
    transaction_name: str = "transaction",
    error_factory: ErrorFactory | None = None,
    **context: Any,
) -> Any:
    """
    Execute a transaction-wrapped operation with simple retry support.

    This helper is intended only for idempotent operations.

    Args:
        resource_factory: Factory that returns a fresh transaction resource.
        operation: Callable to execute.
        attempts: Maximum attempts, must be >= 1.
        should_retry: Optional predicate to decide whether to retry an error.
        logger: Optional structured logger.
        transaction_name: Human-readable transaction name.
        error_factory: Optional exception mapper.
        **context: Structured log context.

    Returns:
        The operation result.

    Raises:
        ProjectPulseError: Final mapped error after retries are exhausted.
        ValueError: If attempts < 1.
    """
    if attempts < 1:
        raise ValueError("attempts must be >= 1")

    active_logger = logger or _DEFAULT_LOGGER
    retry_predicate = should_retry or (lambda exc: not isinstance(exc, ProjectPulseError))

    last_error: Exception | None = None

    for attempt in range(1, attempts + 1):
        try:
            return run_in_transaction(
                resource_factory(),
                operation,
                logger=active_logger,
                transaction_name=transaction_name,
                error_factory=error_factory,
                attempt=attempt,
                max_attempts=attempts,
                **context,
            )
        except Exception as exc:  # noqa: BLE001
            last_error = exc

            if attempt >= attempts or not retry_predicate(exc):
                raise

            log_event(
                active_logger,
                event_name="transaction_retry_scheduled",
                message="Retrying transaction",
                transaction_name=transaction_name,
                attempt=attempt,
                max_attempts=attempts,
                error_type=type(exc).__name__,
                **context,
            )

    if last_error is not None:
        raise last_error

    raise RuntimeError("retry_transaction reached an impossible state")
