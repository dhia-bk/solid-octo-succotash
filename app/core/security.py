"""
Security-safe runtime helpers for Project Pulse Knowledge Graph.

Purpose:
- prevent raw secrets from leaking into logs
- centralize required/optional environment variable access
- provide safe redacted views of config payloads and DSNs

Design rules:
- never log raw secrets
- treat env lookups as part of configuration validation
- sanitize nested dict/list structures recursively
"""

from __future__ import annotations

import os
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from app.core.exceptions import MissingEnvironmentVariableError

# Sensitive key detection

_SENSITIVE_FIELD_FRAGMENTS: tuple[str, ...] = (
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


def is_sensitive_key(key: str) -> bool:
    """
    Return True if a config/log field name should be treated as sensitive.
    """
    lowered = key.lower()
    return any(fragment in lowered for fragment in _SENSITIVE_FIELD_FRAGMENTS)


# Primitive masking helpers


def mask_secret(value: str | None, *, visible_prefix: int = 2, visible_suffix: int = 2) -> str:
    """
    Mask a secret string while preserving a small readable prefix/suffix.

    Examples:
        "abcd1234" -> "ab***34"
        "abc" -> "***"

    Args:
        value: Raw secret value.
        visible_prefix: Number of visible leading characters.
        visible_suffix: Number of visible trailing characters.

    Returns:
        Masked string safe for logs.
    """
    if value is None:
        return "***"

    if not value:
        return "***"

    text = str(value)

    if len(text) <= visible_prefix + visible_suffix + 1:
        return "***"

    return f"{text[:visible_prefix]}***{text[-visible_suffix:]}"


def mask_password(value: str | None) -> str:
    """Mask a password value."""
    return mask_secret(value)


def mask_api_key(value: str | None) -> str:
    """Mask an API key value."""
    return mask_secret(value, visible_prefix=3, visible_suffix=2)


def mask_token(value: str | None) -> str:
    """Mask a token value."""
    return mask_secret(value, visible_prefix=3, visible_suffix=2)


# URI / DSN redaction helpers


def redact_uri(uri: str | None) -> str:
    """
    Redact credentials and sensitive query parameters from a URI/DSN.

    Handles examples such as:
    - mysql+pymysql://user:password@host:3306/db
    - postgres://user:password@host/db?sslmode=require
    - https://host/path?token=abc123

    Returns:
        Redacted URI safe for logs.
    """
    if not uri:
        return "***"

    try:
        parts = urlsplit(uri)
    except Exception:
        return mask_secret(uri)

    username = parts.username or ""
    password = parts.password or ""

    host = parts.hostname or ""
    port = f":{parts.port}" if parts.port is not None else ""

    netloc = host + port
    if username:
        netloc = f"{username}:{mask_password(password)}@{netloc}"

    query_items = []
    for key, value in parse_qsl(parts.query, keep_blank_values=True):
        if is_sensitive_key(key):
            query_items.append((key, mask_secret(value)))
        else:
            query_items.append((key, value))

    safe_query = urlencode(query_items)

    return urlunsplit((parts.scheme, netloc, parts.path, safe_query, parts.fragment))


def redact_mysql_credentials(
    *,
    host: str | None,
    port: int | str | None,
    database: str | None,
    user: str | None,
    password: str | None,
) -> dict[str, Any]:
    """
    Return a safe dict representation of MySQL connection settings.
    """
    return {
        "host": host,
        "port": port,
        "database": database,
        "user": user,
        "password": mask_password(password),
    }


def redact_neo4j_config(
    *,
    uri: str | None,
    user: str | None,
    password: str | None,
    database: str | None,
) -> dict[str, Any]:
    """
    Return a safe dict representation of Neo4j connection settings.
    """
    return {
        "uri": redact_uri(uri),
        "user": user,
        "password": mask_password(password),
        "database": database,
    }


def redact_api_config(
    *,
    api_key_enabled: bool | None,
    api_key_header: str | None,
    api_key_value: str | None,
) -> dict[str, Any]:
    """
    Return a safe dict representation of API security settings.
    """
    return {
        "api_key_enabled": api_key_enabled,
        "api_key_header": api_key_header,
        "api_key_value": mask_api_key(api_key_value),
    }


# Environment lookup helpers


def get_required_env(name: str, *, strip: bool = True) -> str:
    """
    Fetch a required environment variable.

    Args:
        name: Environment variable name.
        strip: Whether to strip surrounding whitespace.

    Returns:
        Environment value.

    Raises:
        MissingEnvironmentVariableError: If the variable is missing or blank.
    """
    value = os.getenv(name)

    if value is None:
        raise MissingEnvironmentVariableError(
            "Required environment variable is missing",
            env_var=name,
        )

    if strip:
        value = value.strip()

    if value == "":
        raise MissingEnvironmentVariableError(
            "Required environment variable is blank",
            env_var=name,
        )

    return value


def get_optional_env(
    name: str,
    *,
    default: str | None = None,
    strip: bool = True,
) -> str | None:
    """
    Fetch an optional environment variable.

    Args:
        name: Environment variable name.
        default: Default value if missing.
        strip: Whether to strip surrounding whitespace.

    Returns:
        Value or default.
    """
    value = os.getenv(name, default)

    if value is None:
        return None

    if strip:
        value = value.strip()

    return value or default


def get_optional_env_bool(
    name: str,
    *,
    default: bool | None = None,
) -> bool | None:
    """
    Fetch an optional boolean environment variable.

    Accepted truthy values:
    - true, 1, yes, y, on

    Accepted falsy values:
    - false, 0, no, n, off
    """
    raw = os.getenv(name)

    if raw is None:
        return default

    value = raw.strip().lower()

    if value in {"true", "1", "yes", "y", "on"}:
        return True

    if value in {"false", "0", "no", "n", "off"}:
        return False

    return default


def get_optional_env_int(
    name: str,
    *,
    default: int | None = None,
) -> int | None:
    """
    Fetch an optional integer environment variable.
    """
    raw = os.getenv(name)

    if raw is None or raw.strip() == "":
        return default

    try:
        return int(raw.strip())
    except ValueError:
        return default


# Recursive config sanitization helpers


def sanitize_config_value(key: str, value: Any) -> Any:
    """
    Sanitize a config value for safe display/logging.

    Rules:
    - sensitive keys are masked
    - URI-like strings are redacted when key suggests a connection field
    - dicts/lists/tuples are sanitized recursively
    """
    if is_sensitive_key(key):
        if isinstance(value, str) and ("://" in value or key.lower() in {"uri", "dsn", "url"}):
            return redact_uri(value)
        return mask_secret(None if value is None else str(value))

    if isinstance(value, dict):
        return sanitize_config_payload(value)

    if isinstance(value, list):
        return [sanitize_config_value(key, item) for item in value]

    if isinstance(value, tuple):
        return tuple(sanitize_config_value(key, item) for item in value)

    return value


def sanitize_config_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    """
    Recursively sanitize a configuration dictionary for safe logging.
    """
    if not payload:
        return {}

    return {key: sanitize_config_value(key, value) for key, value in payload.items()}


def build_safe_startup_config_summary(
    *,
    app: dict[str, Any] | None = None,
    api: dict[str, Any] | None = None,
    mysql: dict[str, Any] | None = None,
    neo4j: dict[str, Any] | None = None,
    metadata_db: dict[str, Any] | None = None,
    security: dict[str, Any] | None = None,
    runtime: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Build a sanitized startup config summary suitable for structured logs.
    """
    summary = {
        "app": app or {},
        "api": api or {},
        "mysql": mysql or {},
        "neo4j": neo4j or {},
        "metadata_db": metadata_db or {},
        "security": security or {},
        "runtime": runtime or {},
    }
    return sanitize_config_payload(summary)
