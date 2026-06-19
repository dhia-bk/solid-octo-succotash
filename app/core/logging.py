"""
Structured logging utilities for Project Pulse Knowledge Graph.

Design goals:
- Provide a shared logger factory for all modules.
- Support structured context fields consistently.
- Load logging configuration from YAML.
- Sanitize secrets before emission.
- Keep this module independent from late-stage application code.

Usage:
    from app.core.logging import get_logger, log_pipeline_started

    logger = get_logger(__name__)
    log_pipeline_started(logger, pipeline_name="identity_pipeline", run_id="...")
"""

from __future__ import annotations

import logging
import logging.config
from collections.abc import MutableMapping
from pathlib import Path
from typing import Any

import yaml

from app.core.constants import (
    DEFAULT_APP_NAME,
    EVENT_ANALYTICS_FINISHED,
    EVENT_ANALYTICS_STARTED,
    EVENT_EXTRACTION_FINISHED,
    EVENT_EXTRACTION_STARTED,
    EVENT_LOAD_FINISHED,
    EVENT_LOAD_STARTED,
    EVENT_PIPELINE_FINISHED,
    EVENT_PIPELINE_STARTED,
    EVENT_TRANSFORMATION_FINISHED,
    EVENT_TRANSFORMATION_STARTED,
    EVENT_VALIDATION_FAILED,
)
from app.core.exceptions import ConfigurationError
from app.core.time import format_log_timestamp

# ============================================================================
# Module state
# ============================================================================

_LOGGING_CONFIGURED: bool = False

# Sensitive keys are matched by lowercase name.
_SENSITIVE_FIELD_NAMES: tuple[str, ...] = (
    "password",
    "passwd",
    "secret",
    "token",
    "api_key",
    "apikey",
    "authorization",
    "auth",
    "dsn",
    "uri",
    "url",
    "connection_string",
    "private_key",
    "access_key",
    "refresh_token",
)

#  Secret sanitization


def _is_sensitive_key(key: str) -> bool:
    """
    Return True if a field name should be treated as sensitive.
    """
    lowered = key.lower()
    return any(fragment in lowered for fragment in _SENSITIVE_FIELD_NAMES)


def _mask_string(value: str) -> str:
    """
    Mask a sensitive string while preserving minimal debuggability.
    """
    if not value:
        return "***"

    if len(value) <= 4:
        return "*" * len(value)

    return f"{value[:2]}***{value[-2:]}"


def sanitize_log_value(key: str, value: Any) -> Any:
    """
    Sanitize a value for safe logging.

    Rules:
    - known sensitive keys are masked
    - nested dicts/lists are sanitized recursively
    - primitive values are preserved when safe
    """
    if _is_sensitive_key(key):
        return _mask_string(str(value))

    if isinstance(value, dict):
        return sanitize_log_context(value)

    if isinstance(value, list):
        return [sanitize_log_value(key, item) for item in value]

    if isinstance(value, tuple):
        return tuple(sanitize_log_value(key, item) for item in value)

    return value


def sanitize_log_context(context: dict[str, Any] | None) -> dict[str, Any]:
    """
    Sanitize a structured context dictionary for safe logging.
    """
    if not context:
        return {}

    return {key: sanitize_log_value(key, value) for key, value in context.items()}


# Logging configuration


def load_logging_config(config_path: str | Path) -> dict[str, Any]:
    """
    Load logging configuration from a YAML file.

    Args:
        config_path: Path to logging YAML config.

    Returns:
        Parsed logging config dictionary.

    Raises:
        ConfigurationError: If the config file is missing or invalid.
    """
    path = Path(config_path)

    if not path.exists():
        raise ConfigurationError(
            "Logging configuration file does not exist",
            config_path=str(path),
        )

    try:
        with path.open("r", encoding="utf-8") as handle:
            loaded = yaml.safe_load(handle) or {}
    except OSError as exc:
        raise ConfigurationError(
            "Failed to read logging configuration file",
            config_path=str(path),
        ) from exc
    except yaml.YAMLError as exc:
        raise ConfigurationError(
            "Invalid YAML in logging configuration file",
            config_path=str(path),
        ) from exc

    if not isinstance(loaded, dict):
        raise ConfigurationError(
            "Logging configuration must be a dictionary",
            config_path=str(path),
        )

    return loaded


def configure_logging(config_path: str | Path) -> None:
    """
    Configure the Python logging system from YAML.

    Safe to call multiple times; configuration is only applied once per process.
    """
    global _LOGGING_CONFIGURED

    if _LOGGING_CONFIGURED:
        return

    config = load_logging_config(config_path)

    try:
        logging.config.dictConfig(config)
    except Exception as exc:  # noqa: BLE001
        raise ConfigurationError(
            "Failed to apply logging configuration",
            config_path=str(config_path),
        ) from exc

    _LOGGING_CONFIGURED = True


# Logger adapter


class ProjectPulseLoggerAdapter(logging.LoggerAdapter):
    """
    Logger adapter that merges structured context and sanitizes sensitive values.
    """

    def process(
        self,
        msg: object,
        kwargs: MutableMapping[str, Any],
    ) -> tuple[object, MutableMapping[str, Any]]:
        extra = dict(self.extra or {})
        incoming_extra = kwargs.pop("extra", {}) or {}

        if not isinstance(incoming_extra, dict):
            incoming_extra = {"extra_payload": incoming_extra}

        merged_extra = {**extra, **incoming_extra}
        merged_extra = sanitize_log_context(merged_extra)

        kwargs["extra"] = merged_extra
        return msg, kwargs


# Logger factory


def get_logger(name: str, **base_context: Any) -> ProjectPulseLoggerAdapter:
    """
    Return a configured structured logger for a module.

    Args:
        name: Logger/module name.
        **base_context: Optional base context bound to the logger.

    Returns:
        ProjectPulseLoggerAdapter
    """
    logger = logging.getLogger(name)
    return ProjectPulseLoggerAdapter(logger, sanitize_log_context(base_context))


def bind_logger(logger: ProjectPulseLoggerAdapter, **context: Any) -> ProjectPulseLoggerAdapter:
    """
    Return a new logger adapter with additional bound context.
    """
    merged = dict(logger.extra or {})
    merged.update(sanitize_log_context(context))
    return ProjectPulseLoggerAdapter(logger.logger, merged)


# Core structured logging helper


def log_event(
    logger: logging.Logger | ProjectPulseLoggerAdapter,
    *,
    event_name: str,
    level: int = logging.INFO,
    message: str | None = None,
    **context: Any,
) -> None:
    """
    Log a structured event with a canonical event name and timestamp.

    Args:
        logger: Logger or logger adapter.
        event_name: Canonical event identifier.
        level: Logging level.
        message: Optional human-readable message.
        **context: Structured context payload.
    """
    payload = {
        "event_name": event_name,
        "event_ts": format_log_timestamp(),
        **sanitize_log_context(context),
    }

    logger.log(level, message or event_name, extra=payload)


# Standard event helpers


def log_pipeline_started(
    logger: logging.Logger | ProjectPulseLoggerAdapter,
    *,
    pipeline_name: str,
    run_id: str,
    env: str | None = None,
    **context: Any,
) -> None:
    log_event(
        logger,
        event_name=EVENT_PIPELINE_STARTED,
        message="Pipeline started",
        pipeline_name=pipeline_name,
        run_id=run_id,
        env=env,
        started_at=format_log_timestamp(),
        **context,
    )


def log_pipeline_finished(
    logger: logging.Logger | ProjectPulseLoggerAdapter,
    *,
    pipeline_name: str,
    run_id: str,
    status: str = "success",
    duration_ms: int | None = None,
    **context: Any,
) -> None:
    log_event(
        logger,
        event_name=EVENT_PIPELINE_FINISHED,
        message="Pipeline finished",
        pipeline_name=pipeline_name,
        run_id=run_id,
        status=status,
        finished_at=format_log_timestamp(),
        duration_ms=duration_ms,
        **context,
    )


def log_extraction_started(
    logger: logging.Logger | ProjectPulseLoggerAdapter,
    *,
    table_name: str,
    pipeline_name: str | None = None,
    run_id: str | None = None,
    **context: Any,
) -> None:
    log_event(
        logger,
        event_name=EVENT_EXTRACTION_STARTED,
        message="Extraction started",
        table_name=table_name,
        pipeline_name=pipeline_name,
        run_id=run_id,
        **context,
    )


def log_extraction_finished(
    logger: logging.Logger | ProjectPulseLoggerAdapter,
    *,
    table_name: str,
    record_count: int,
    pipeline_name: str | None = None,
    run_id: str | None = None,
    duration_ms: int | None = None,
    **context: Any,
) -> None:
    log_event(
        logger,
        event_name=EVENT_EXTRACTION_FINISHED,
        message="Extraction finished",
        table_name=table_name,
        record_count=record_count,
        pipeline_name=pipeline_name,
        run_id=run_id,
        duration_ms=duration_ms,
        **context,
    )


def log_transformation_started(
    logger: logging.Logger | ProjectPulseLoggerAdapter,
    *,
    table_name: str | None = None,
    pipeline_name: str | None = None,
    run_id: str | None = None,
    **context: Any,
) -> None:
    log_event(
        logger,
        event_name=EVENT_TRANSFORMATION_STARTED,
        message="Transformation started",
        table_name=table_name,
        pipeline_name=pipeline_name,
        run_id=run_id,
        **context,
    )


def log_transformation_finished(
    logger: logging.Logger | ProjectPulseLoggerAdapter,
    *,
    record_count: int | None = None,
    table_name: str | None = None,
    pipeline_name: str | None = None,
    run_id: str | None = None,
    duration_ms: int | None = None,
    **context: Any,
) -> None:
    log_event(
        logger,
        event_name=EVENT_TRANSFORMATION_FINISHED,
        message="Transformation finished",
        record_count=record_count,
        table_name=table_name,
        pipeline_name=pipeline_name,
        run_id=run_id,
        duration_ms=duration_ms,
        **context,
    )


def log_load_started(
    logger: logging.Logger | ProjectPulseLoggerAdapter,
    *,
    pipeline_name: str | None = None,
    run_id: str | None = None,
    batch_id: str | None = None,
    graph_name: str | None = None,
    **context: Any,
) -> None:
    log_event(
        logger,
        event_name=EVENT_LOAD_STARTED,
        message="Load started",
        pipeline_name=pipeline_name,
        run_id=run_id,
        batch_id=batch_id,
        graph_name=graph_name,
        **context,
    )


def log_load_finished(
    logger: logging.Logger | ProjectPulseLoggerAdapter,
    *,
    pipeline_name: str | None = None,
    run_id: str | None = None,
    batch_id: str | None = None,
    record_count: int | None = None,
    duration_ms: int | None = None,
    **context: Any,
) -> None:
    log_event(
        logger,
        event_name=EVENT_LOAD_FINISHED,
        message="Load finished",
        pipeline_name=pipeline_name,
        run_id=run_id,
        batch_id=batch_id,
        record_count=record_count,
        duration_ms=duration_ms,
        **context,
    )


def log_validation_failure(
    logger: logging.Logger | ProjectPulseLoggerAdapter,
    *,
    error: str,
    pipeline_name: str | None = None,
    table_name: str | None = None,
    run_id: str | None = None,
    **context: Any,
) -> None:
    log_event(
        logger,
        event_name=EVENT_VALIDATION_FAILED,
        level=logging.ERROR,
        message="Validation failed",
        error=error,
        pipeline_name=pipeline_name,
        table_name=table_name,
        run_id=run_id,
        **context,
    )


def log_analytics_started(
    logger: logging.Logger | ProjectPulseLoggerAdapter,
    *,
    job_name: str,
    run_id: str,
    graph_name: str | None = None,
    version: str | None = None,
    **context: Any,
) -> None:
    log_event(
        logger,
        event_name=EVENT_ANALYTICS_STARTED,
        message="Analytics job started",
        job_name=job_name,
        run_id=run_id,
        graph_name=graph_name,
        version=version,
        started_at=format_log_timestamp(),
        **context,
    )


def log_analytics_finished(
    logger: logging.Logger | ProjectPulseLoggerAdapter,
    *,
    job_name: str,
    run_id: str,
    graph_name: str | None = None,
    version: str | None = None,
    status: str = "success",
    duration_ms: int | None = None,
    **context: Any,
) -> None:
    log_event(
        logger,
        event_name=EVENT_ANALYTICS_FINISHED,
        message="Analytics job finished",
        job_name=job_name,
        run_id=run_id,
        graph_name=graph_name,
        version=version,
        status=status,
        duration_ms=duration_ms,
        finished_at=format_log_timestamp(),
        **context,
    )


# Convenience startup helper


def log_startup_summary(
    logger: logging.Logger | ProjectPulseLoggerAdapter,
    *,
    app_name: str = DEFAULT_APP_NAME,
    env: str,
    config_summary: dict[str, Any] | None = None,
) -> None:
    """
    Emit a sanitized startup summary log.
    """
    log_event(
        logger,
        event_name="startup_summary",
        message="Application startup summary",
        app_name=app_name,
        env=env,
        config_summary=sanitize_log_context(config_summary or {}),
    )
