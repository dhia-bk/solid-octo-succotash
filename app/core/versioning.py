"""
Versioning and run-stamp utilities for Project Pulse Knowledge Graph.

Design rules:
- All runtime artifacts must be traceable to a logical version and a run ID.
- Run IDs must be unique, sortable, readable, and safe for logs and DB storage.
- No later module should invent its own version or run-ID scheme.
- Version composition must be deterministic.
"""

from __future__ import annotations

import re
from typing import Final

from app.core.exceptions import ModelVersionError, ValidationError
from app.core.time import format_run_id_timestamp, utc_now

# ============================================================================
# Static version constants
# Update these intentionally when behavior changes.
# ============================================================================

ONTOLOGY_VERSION: Final[str] = "1.0.0"
WEIGHTING_VERSION: Final[str] = "1.0.0"
INFERENCE_VERSION: Final[str] = "1.0.0"
PROJECTION_VERSION: Final[str] = "1.0.0"
SERVING_VERSION: Final[str] = "1.0.0"

VERSION_COMPONENTS: Final[tuple[str, ...]] = (
    ONTOLOGY_VERSION,
    WEIGHTING_VERSION,
    INFERENCE_VERSION,
    PROJECTION_VERSION,
    SERVING_VERSION,
)

# ============================================================================
# Regex helpers
# ============================================================================

_SEMVER_RE: Final[re.Pattern[str]] = re.compile(r"^\d+\.\d+\.\d+$")
_SAFE_VERSION_TEXT_RE: Final[re.Pattern[str]] = re.compile(r"[^a-zA-Z0-9._-]+")

# ============================================================================
# Normalization helpers
# ============================================================================


def normalize_version(value: str) -> str:
    """
    Normalize a human-readable version string into a safe canonical form.

    Rules:
    - strip outer whitespace
    - replace internal unsafe character runs with "-"
    - preserve dots, underscores, and hyphens

    Args:
        value: Raw version string.

    Returns:
        Safe normalized version string.

    Raises:
        ValidationError: If the input is empty after normalization.
    """
    cleaned = value.strip()
    cleaned = _SAFE_VERSION_TEXT_RE.sub("-", cleaned)
    cleaned = cleaned.strip("-")

    if not cleaned:
        raise ValidationError(
            "Version string cannot be empty",
            raw_value=value,
        )

    return cleaned


def validate_semver(version: str) -> str:
    """
    Validate that a version string follows MAJOR.MINOR.PATCH format.

    Args:
        version: Version string.

    Returns:
        The same version if valid.

    Raises:
        ModelVersionError: If the version is not valid semver.
    """
    normalized = normalize_version(version)

    if not _SEMVER_RE.match(normalized):
        raise ModelVersionError(
            "Invalid semantic version format",
            version=version,
            expected_format="MAJOR.MINOR.PATCH",
        )

    return normalized


def parse_semver(version: str) -> tuple[int, int, int]:
    """
    Parse a semantic version string into integer components.

    Args:
        version: Semver string.

    Returns:
        Tuple of (major, minor, patch).
    """
    validated = validate_semver(version)
    major, minor, patch = validated.split(".")
    return int(major), int(minor), int(patch)


# ============================================================================
# Composition helpers
# ============================================================================


def compose_versioned_stamp(version: str, timestamp: str) -> str:
    """
    Compose a deterministic versioned stamp.

    Example:
        1.0.0__20260123T121530Z

    Args:
        version: Logical version string.
        timestamp: UTC timestamp component.

    Returns:
        Composed version stamp.
    """
    normalized_version = normalize_version(version)
    return f"{normalized_version}__{timestamp}"


def compose_named_version(name: str, version: str) -> str:
    """
    Compose a readable named version.

    Example:
        weighting__1.0.0

    Args:
        name: Logical component name.
        version: Version string.

    Returns:
        Named version string.
    """
    safe_name = normalize_version(name).lower()
    safe_version = normalize_version(version)
    return f"{safe_name}__{safe_version}"


def compose_pipeline_run_id(pipeline_name: str, timestamp: str | None = None) -> str:
    """
    Compose a pipeline run ID.

    Example:
        full_backfill_pipeline__20260123T121530Z

    Args:
        pipeline_name: Canonical pipeline name.
        timestamp: Optional preformatted UTC timestamp.

    Returns:
        Stable pipeline run ID.
    """
    safe_name = normalize_version(pipeline_name).lower()
    ts = timestamp or format_run_id_timestamp(utc_now())
    return f"{safe_name}__{ts}"


def compose_model_run_id(
    model_name: str,
    version: str,
    timestamp: str | None = None,
) -> str:
    """
    Compose a model execution run ID.

    Example:
        leiden__1.0.0__20260123T121530Z

    Args:
        model_name: Logical model/job name.
        version: Logical model version.
        timestamp: Optional timestamp.

    Returns:
        Stable model run ID.
    """
    safe_name = normalize_version(model_name).lower()
    safe_version = normalize_version(version)
    ts = timestamp or format_run_id_timestamp(utc_now())
    return f"{safe_name}__{safe_version}__{ts}"


# ============================================================================
# Run stamp helpers
# ============================================================================


def generate_run_id(prefix: str) -> str:
    """
    Generate a generic run ID using current UTC time.

    Example:
        sync__20260123T121530Z
    """
    return compose_pipeline_run_id(prefix)


def generate_analytics_job_id(job_name: str, version: str) -> str:
    """
    Generate a run ID for an analytics job.

    Example:
        leiden__1.0.0__20260123T121530Z
    """
    return compose_model_run_id(job_name, version)


def generate_inference_run_id() -> str:
    """
    Generate a run ID for inference execution.
    """
    return compose_model_run_id("inference", INFERENCE_VERSION)


def generate_backfill_run_id() -> str:
    """
    Generate a run ID for a full backfill execution.
    """
    return compose_pipeline_run_id("full_backfill")


def generate_incremental_sync_run_id() -> str:
    """
    Generate a run ID for an incremental sync execution.
    """
    return compose_pipeline_run_id("incremental_sync")


def generate_serving_materialization_run_id() -> str:
    """
    Generate a run ID for serving materialization execution.
    """
    return compose_model_run_id("serving_materialization", SERVING_VERSION)


def generate_checkpoint_version_marker(version: str) -> str:
    """
    Generate a version marker for checkpoint state.

    Example:
        checkpoint__1.0.0__20260123T121530Z
    """
    return compose_model_run_id("checkpoint", version)


# ============================================================================
# Version marker helpers
# ============================================================================


def get_weighting_version_marker() -> str:
    """
    Return the logical weighting version marker.
    """
    return compose_named_version("weighting", WEIGHTING_VERSION)


def get_inference_version_marker() -> str:
    """
    Return the logical inference version marker.
    """
    return compose_named_version("inference", INFERENCE_VERSION)


def get_projection_version_marker() -> str:
    """
    Return the logical projection version marker.
    """
    return compose_named_version("projection", PROJECTION_VERSION)


def get_serving_version_marker() -> str:
    """
    Return the logical serving version marker.
    """
    return compose_named_version("serving", SERVING_VERSION)


def get_ontology_version_marker() -> str:
    """
    Return the logical ontology version marker.
    """
    return compose_named_version("ontology", ONTOLOGY_VERSION)


# ============================================================================
# Compatibility helpers
# ============================================================================


def semver_equal(left: str, right: str) -> bool:
    """
    Return True if two semantic versions are exactly equal.
    """
    return parse_semver(left) == parse_semver(right)


def semver_greater_than(left: str, right: str) -> bool:
    """
    Return True if left semantic version is greater than right.
    """
    return parse_semver(left) > parse_semver(right)


def semver_compatible(config_version: str, runtime_version: str) -> bool:
    """
    Basic compatibility rule:
    - major versions must match
    - runtime minor/patch may be greater than or equal to config version

    Examples:
        config=1.2.0 runtime=1.2.0 -> True
        config=1.2.0 runtime=1.3.1 -> True
        config=1.2.0 runtime=2.0.0 -> False
        config=1.2.0 runtime=1.1.9 -> False
    """
    c_major, c_minor, c_patch = parse_semver(config_version)
    r_major, r_minor, r_patch = parse_semver(runtime_version)

    if c_major != r_major:
        return False

    return (r_minor, r_patch) >= (c_minor, c_patch)


def assert_model_version_matches_config(
    *,
    component_name: str,
    config_version: str,
    runtime_version: str,
) -> None:
    """
    Assert that a runtime model version is compatible with the configured version.

    Raises:
        ModelVersionError: If versions are incompatible.
    """
    if not semver_compatible(config_version, runtime_version):
        raise ModelVersionError(
            "Runtime model version is incompatible with configured version",
            component_name=component_name,
            config_version=config_version,
            runtime_version=runtime_version,
        )


# ============================================================================
# Snapshot helpers
# ============================================================================


def get_platform_version_snapshot() -> dict[str, str]:
    """
    Return the current platform version snapshot.

    Useful for:
    - job metadata
    - model registry
    - run manifests
    """
    return {
        "ontology_version": ONTOLOGY_VERSION,
        "weighting_version": WEIGHTING_VERSION,
        "inference_version": INFERENCE_VERSION,
        "projection_version": PROJECTION_VERSION,
        "serving_version": SERVING_VERSION,
    }
