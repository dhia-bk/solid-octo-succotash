"""
Shared abstractions for the validation layer.

Every public check function across the validation package returns a
ValidationResult or list[ValidationResult] — never raises on failure.
This module defines the types, the base class, and the report factory.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any

from app.core.logging import get_logger
from app.core.time import format_iso_timestamp, utc_now


class ValidationSeverity(str, Enum):
    CRITICAL = "critical"   # halt pipeline
    ERROR    = "error"      # log, skip batch
    WARNING  = "warning"    # log only
    INFO     = "info"       # telemetry


@dataclass(frozen=True)
class ValidationResult:
    check_name: str
    passed: bool
    severity: ValidationSeverity
    source: str
    message: str
    details: dict[str, Any]
    run_id: str | None = None
    checked_at: str | None = None


@dataclass
class ValidationReport:
    run_id: str
    results: list[ValidationResult]
    started_at: str
    finished_at: str | None = None

    def has_critical(self) -> bool:
        return any(
            r.severity == ValidationSeverity.CRITICAL and not r.passed
            for r in self.results
        )

    def has_errors(self) -> bool:
        return any(
            r.severity in (ValidationSeverity.CRITICAL, ValidationSeverity.ERROR)
            and not r.passed
            for r in self.results
        )

    def failures(self) -> list[ValidationResult]:
        return [r for r in self.results if not r.passed]

    def by_severity(self, severity: ValidationSeverity) -> list[ValidationResult]:
        return [r for r in self.results if r.severity == severity]

    def summary(self) -> dict[str, Any]:
        total = len(self.results)
        failed = len(self.failures())
        return {
            "run_id": self.run_id,
            "total_checks": total,
            "passed": total - failed,
            "failed": failed,
            "has_critical": self.has_critical(),
            "has_errors": self.has_errors(),
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "by_severity": {
                sev.value: len(self.by_severity(sev))
                for sev in ValidationSeverity
            },
        }


class BaseValidator(ABC):
    def __init__(self, run_id: str) -> None:
        self._run_id = run_id
        self._logger = get_logger(f"{type(self).__module__}.{type(self).__name__}")

    @abstractmethod
    def validate(self, *args: Any, **kwargs: Any) -> list[ValidationResult]: ...

    def _pass(
        self,
        check_name: str,
        source: str,
        message: str,
        **details: Any,
    ) -> ValidationResult:
        return ValidationResult(
            check_name=check_name,
            passed=True,
            severity=ValidationSeverity.INFO,
            source=source,
            message=message,
            details=dict(details),
            run_id=self._run_id,
            checked_at=format_iso_timestamp(utc_now()),
        )

    def _fail(
        self,
        check_name: str,
        source: str,
        severity: ValidationSeverity,
        message: str,
        **details: Any,
    ) -> ValidationResult:
        return ValidationResult(
            check_name=check_name,
            passed=False,
            severity=severity,
            source=source,
            message=message,
            details=dict(details),
            run_id=self._run_id,
            checked_at=format_iso_timestamp(utc_now()),
        )

    def _warn(
        self,
        check_name: str,
        source: str,
        message: str,
        **details: Any,
    ) -> ValidationResult:
        return ValidationResult(
            check_name=check_name,
            passed=False,
            severity=ValidationSeverity.WARNING,
            source=source,
            message=message,
            details=dict(details),
            run_id=self._run_id,
            checked_at=format_iso_timestamp(utc_now()),
        )


def build_validation_report(
    run_id: str,
    results: list[ValidationResult],
    *,
    started_at: str | None = None,
) -> ValidationReport:
    """Assemble a ValidationReport from a flat list of results."""
    return ValidationReport(
        run_id=run_id,
        results=results,
        started_at=started_at or format_iso_timestamp(utc_now()),
        finished_at=format_iso_timestamp(utc_now()),
    )