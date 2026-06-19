import pytest

from app.core.exceptions import MissingEnvironmentVariableError
from app.core.security import (
    build_safe_startup_config_summary,
    get_optional_env,
    get_optional_env_bool,
    get_optional_env_int,
    get_required_env,
    is_sensitive_key,
    mask_secret,
    redact_uri,
    sanitize_config_payload,
)


def test_mask_secret_masks_middle_of_value() -> None:
    assert mask_secret("supersecretvalue") == "su***ue"
    assert mask_secret("abc") == "***"
    assert mask_secret(None) == "***"


def test_is_sensitive_key_detects_secret_like_fields() -> None:
    assert is_sensitive_key("password") is True
    assert is_sensitive_key("api_key") is True
    assert is_sensitive_key("username") is False


def test_redact_uri_masks_credentials_and_query_secret() -> None:
    uri = "mysql://user:password@localhost:3306/db?token=abc123&sslmode=require"

    redacted = redact_uri(uri)

    assert "password" not in redacted
    assert "abc123" not in redacted
    assert "user:" in redacted
    assert "localhost:3306" in redacted


def test_get_required_env_returns_stripped_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEST_REQUIRED_ENV", "  hello  ")

    assert get_required_env("TEST_REQUIRED_ENV") == "hello"


def test_get_required_env_raises_for_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TEST_REQUIRED_ENV", raising=False)

    with pytest.raises(MissingEnvironmentVariableError):
        get_required_env("TEST_REQUIRED_ENV")


def test_get_optional_env_helpers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEST_OPTIONAL_TEXT", "  value  ")
    monkeypatch.setenv("TEST_OPTIONAL_BOOL", "yes")
    monkeypatch.setenv("TEST_OPTIONAL_INT", "42")

    assert get_optional_env("TEST_OPTIONAL_TEXT") == "value"
    assert get_optional_env_bool("TEST_OPTIONAL_BOOL") is True
    assert get_optional_env_int("TEST_OPTIONAL_INT") == 42


def test_sanitize_config_payload_masks_sensitive_values() -> None:
    payload = {
        "user": "alice",
        "password": "supersecretvalue",
        "nested": {"api_key": "abcdef123456"},
    }

    sanitized = sanitize_config_payload(payload)

    assert sanitized["user"] == "alice"
    assert sanitized["password"] != "supersecretvalue"
    assert sanitized["nested"]["api_key"] != "abcdef123456"


def test_build_safe_startup_config_summary_masks_db_passwords() -> None:
    summary = build_safe_startup_config_summary(
        mysql={"host": "localhost", "password": "supersecretvalue"},
        neo4j={"uri": "bolt://neo4j:password@localhost:7687", "password": "anothersecret"},
    )

    assert summary["mysql"]["password"] != "supersecretvalue"
    assert "password" not in summary["neo4j"]["uri"]
    assert summary["neo4j"]["password"] != "anothersecret"
