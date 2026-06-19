"""
Public API for the app.validation package.

Import from here — not from individual modules — to keep callers insulated
from internal file organisation.
"""

from app.validation.base import (
    BaseValidator,
    ValidationReport,
    ValidationResult,
    ValidationSeverity,
    build_validation_report,
)
from app.validation.reconciliation import ReconciliationReport, ReconciliationValidator
from app.validation.source_checks import validate_batch
from app.validation.source_coverage_checks import SourceCoverageValidator, run_all_coverage_checks
from app.validation.transform_checks import validate_graph_write_batch

__all__ = [
    # base types
    "ValidationSeverity",
    "ValidationResult",
    "ValidationReport",
    "BaseValidator",
    "build_validation_report",
    # convenience functions
    "validate_batch",
    "validate_graph_write_batch",
    # reconciliation
    "ReconciliationValidator",
    "ReconciliationReport",
    # coverage
    "SourceCoverageValidator",
    "run_all_coverage_checks",
]