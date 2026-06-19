"""
Low-level assertion primitives for the validation layer.

Every function returns a ValidationResult — never raises on failure.
All callers should import these instead of duplicating condition logic.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.schemas.graph.properties import PII_PROPERTY_NAMES
from app.validation.base import ValidationResult, ValidationSeverity


def _make(
    check_name: str,
    passed: bool,
    severity: ValidationSeverity,
    source: str,
    run_id: str,
    message: str,
    **details: Any,
) -> ValidationResult:
    from app.core.time import format_iso_timestamp, utc_now

    return ValidationResult(
        check_name=check_name,
        passed=passed,
        severity=severity,
        source=source,
        message=message,
        details=dict(details),
        run_id=run_id,
        checked_at=format_iso_timestamp(utc_now()),
    )


def assert_not_none(
    value: Any,
    field_name: str,
    source: str,
    run_id: str,
    severity: ValidationSeverity = ValidationSeverity.ERROR,
) -> ValidationResult:
    """Return passing result if value is not None, else failing result."""
    check = f"assert_not_none.{field_name}"
    if value is not None:
        return _make(check, True, ValidationSeverity.INFO, source, run_id,
                     f"{field_name} is present")
    return _make(check, False, severity, source, run_id,
                 f"{field_name} is None", field_name=field_name)


def assert_non_empty_string(
    value: Any,
    field_name: str,
    source: str,
    run_id: str,
    severity: ValidationSeverity = ValidationSeverity.ERROR,
) -> ValidationResult:
    """Return passing result if value is a non-empty string after strip."""
    check = f"assert_non_empty_string.{field_name}"
    if isinstance(value, str) and value.strip():
        return _make(check, True, ValidationSeverity.INFO, source, run_id,
                     f"{field_name} is a non-empty string")
    return _make(check, False, severity, source, run_id,
                 f"{field_name} is empty or not a string",
                 field_name=field_name, actual=repr(value))


def assert_in_set(
    value: Any,
    allowed: frozenset,
    field_name: str,
    source: str,
    run_id: str,
    severity: ValidationSeverity = ValidationSeverity.ERROR,
) -> ValidationResult:
    """Return passing result if value is in allowed set."""
    check = f"assert_in_set.{field_name}"
    if value in allowed:
        return _make(check, True, ValidationSeverity.INFO, source, run_id,
                     f"{field_name} is in allowed set")
    return _make(check, False, severity, source, run_id,
                 f"{field_name} value not in allowed set",
                 field_name=field_name, actual=repr(value),
                 allowed=sorted(str(v) for v in allowed))


def assert_within_range(
    value: float | int,
    low: float,
    high: float,
    field_name: str,
    source: str,
    run_id: str,
    severity: ValidationSeverity = ValidationSeverity.WARNING,
) -> ValidationResult:
    """Return passing result if low <= value <= high."""
    check = f"assert_within_range.{field_name}"
    if low <= value <= high:
        return _make(check, True, ValidationSeverity.INFO, source, run_id,
                     f"{field_name} is within [{low}, {high}]")
    return _make(check, False, severity, source, run_id,
                 f"{field_name} is outside [{low}, {high}]",
                 field_name=field_name, actual=value, low=low, high=high)


def assert_no_pii_fields(
    properties: dict[str, Any],
    source: str,
    run_id: str,
) -> ValidationResult:
    """Return passing result if no PII field names exist in properties keys."""
    check = "assert_no_pii_fields"
    violations = sorted(k for k in properties if k in PII_PROPERTY_NAMES)
    if not violations:
        return _make(check, True, ValidationSeverity.INFO, source, run_id,
                     "No PII fields found in properties")
    return _make(check, False, ValidationSeverity.CRITICAL, source, run_id,
                 f"PII fields found in properties: {violations}",
                 pii_fields=violations, field_count=len(violations))


def assert_count_within_threshold(
    actual: int,
    expected: int,
    threshold_pct: float,
    check_name: str,
    source: str,
    run_id: str,
    severity: ValidationSeverity = ValidationSeverity.WARNING,
) -> ValidationResult:
    """Return passing result if abs(actual - expected) / expected <= threshold_pct."""
    if expected == 0:
        passed = actual == 0
        drift = 0.0 if passed else 1.0
    else:
        drift = abs(actual - expected) / expected
        passed = drift <= threshold_pct

    if passed:
        return _make(check_name, True, ValidationSeverity.INFO, source, run_id,
                     f"Count within {threshold_pct:.1%} threshold",
                     actual=actual, expected=expected, drift_pct=round(drift, 4))
    return _make(check_name, False, severity, source, run_id,
                 f"Count drift {drift:.1%} exceeds threshold {threshold_pct:.1%}",
                 actual=actual, expected=expected,
                 drift_pct=round(drift, 4), threshold_pct=threshold_pct)


def assert_no_duplicates(
    values: list[str],
    field_name: str,
    source: str,
    run_id: str,
    severity: ValidationSeverity = ValidationSeverity.ERROR,
) -> ValidationResult:
    """Return passing result if no duplicate values in list."""
    check = f"assert_no_duplicates.{field_name}"
    seen: set[str] = set()
    duplicates: list[str] = []
    for v in values:
        if v in seen and v not in duplicates:
            duplicates.append(v)
        seen.add(v)

    if not duplicates:
        return _make(check, True, ValidationSeverity.INFO, source, run_id,
                     f"No duplicates found in {field_name}")
    return _make(check, False, severity, source, run_id,
                 f"Duplicate values found in {field_name}",
                 field_name=field_name, duplicates=duplicates[:20],
                 duplicate_count=len(duplicates))


def assert_timestamp_is_utc(
    value: str | None,
    field_name: str,
    source: str,
    run_id: str,
    severity: ValidationSeverity = ValidationSeverity.WARNING,
) -> ValidationResult:
    """Return passing result if value is a valid ISO 8601 UTC string or None."""
    check = f"assert_timestamp_is_utc.{field_name}"
    if value is None:
        return _make(check, True, ValidationSeverity.INFO, source, run_id,
                     f"{field_name} is None (acceptable)")
    if not isinstance(value, str):
        return _make(check, False, severity, source, run_id,
                     f"{field_name} is not a string",
                     field_name=field_name, actual_type=type(value).__name__)
    try:
        normalized = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is not None:
            return _make(check, True, ValidationSeverity.INFO, source, run_id,
                         f"{field_name} is a valid UTC timestamp")
        return _make(check, False, severity, source, run_id,
                     f"{field_name} is missing timezone info",
                     field_name=field_name, value=value)
    except ValueError:
        return _make(check, False, severity, source, run_id,
                     f"{field_name} is not a valid ISO 8601 string",
                     field_name=field_name, value=value)