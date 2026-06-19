import re

import pytest

from app.core.exceptions import ModelVersionError, ValidationError
from app.core.versioning import (
    INFERENCE_VERSION,
    ONTOLOGY_VERSION,
    compose_model_run_id,
    compose_named_version,
    compose_pipeline_run_id,
    generate_inference_run_id,
    generate_run_id,
    get_platform_version_snapshot,
    normalize_version,
    parse_semver,
    semver_compatible,
    semver_equal,
    semver_greater_than,
    validate_semver,
)


def test_normalize_version_strips_and_sanitizes() -> None:
    assert normalize_version("  Alpha Release 1  ") == "Alpha-Release-1"


def test_normalize_version_rejects_empty_input() -> None:
    with pytest.raises(ValidationError):
        normalize_version("   ")


def test_validate_semver_accepts_valid_value() -> None:
    assert validate_semver("1.2.3") == "1.2.3"


def test_validate_semver_rejects_invalid_value() -> None:
    with pytest.raises(ModelVersionError):
        validate_semver("1.2")


def test_parse_semver_returns_numeric_tuple() -> None:
    assert parse_semver("2.10.3") == (2, 10, 3)


def test_compose_named_version_is_deterministic() -> None:
    assert compose_named_version("Weighting", "1.0.0") == "weighting__1.0.0"


def test_compose_pipeline_run_id_uses_supplied_timestamp() -> None:
    assert compose_pipeline_run_id("Full Backfill", "20260101T000000Z") == (
        "full-backfill__20260101T000000Z"
    )


def test_compose_model_run_id_uses_supplied_timestamp() -> None:
    assert compose_model_run_id("Leiden", "1.0.0", "20260101T000000Z") == (
        "leiden__1.0.0__20260101T000000Z"
    )


def test_generate_run_id_has_expected_shape() -> None:
    run_id = generate_run_id("test")

    assert re.fullmatch(r"test__\d{8}T\d{6}Z", run_id) is not None


def test_generate_inference_run_id_includes_inference_version() -> None:
    run_id = generate_inference_run_id()

    assert f"inference__{INFERENCE_VERSION}__" in run_id


def test_semver_comparisons_work() -> None:
    assert semver_equal("1.2.3", "1.2.3") is True
    assert semver_greater_than("1.2.4", "1.2.3") is True
    assert semver_compatible("1.2.0", "1.3.1") is True
    assert semver_compatible("1.2.0", "2.0.0") is False
    assert semver_compatible("1.2.0", "1.1.9") is False


def test_platform_version_snapshot_contains_expected_keys() -> None:
    snapshot = get_platform_version_snapshot()

    assert snapshot["ontology_version"] == ONTOLOGY_VERSION
    assert "weighting_version" in snapshot
    assert "inference_version" in snapshot
    assert "projection_version" in snapshot
    assert "serving_version" in snapshot
