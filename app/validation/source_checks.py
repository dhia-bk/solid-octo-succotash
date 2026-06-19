"""
Warehouse source / ExtractorBatch validation.

Runs before transformation. Checks that the batch is structurally sound,
the source is registered, and no PII has leaked into row field names.
"""

from __future__ import annotations

import dataclasses
import sys

from app.contracts.warehouse_rows import ExtractorBatch
from app.mappings.source_to_graph import get_source_artifacts
from app.schemas.graph.properties import PII_PROPERTY_NAMES
from app.validation.base import BaseValidator, ValidationResult, ValidationSeverity


class SourceValidator(BaseValidator):
    """Validates an ExtractorBatch before it enters the transform layer."""

    def validate(self, batch: ExtractorBatch) -> list[ValidationResult]:  # type: ignore[override]
        results: list[ValidationResult] = []

        results.append(self.check_batch_not_empty(batch))
        results.append(self.check_source_name_registered(batch))
        results.append(self.check_inclusion_mode_consistent(batch))
        results.append(self.check_row_types_consistent(batch))

        if batch.rows:
            row_type = type(batch.rows[0])
            schema_module = sys.modules.get(row_type.__module__)
            primary_keys: tuple[str, ...] = getattr(schema_module, "PRIMARY_KEYS", ())
            results.extend(self.check_required_fields_present(batch, primary_keys))

        results.append(self.check_no_pii_in_batch(batch))
        results.append(self.check_freshness_field_present(batch))
        results.append(self.check_row_count_reasonable(batch))

        return results

    def check_batch_not_empty(self, batch: ExtractorBatch) -> ValidationResult:
        """WARN if batch.rows is empty."""
        name = "check_batch_not_empty"
        if batch.rows:
            return self._pass(name, batch.source_name, f"Batch has {batch.row_count} rows")
        return self._warn(name, batch.source_name,
                          "Batch is empty — may indicate extraction failure or stale watermark",
                          row_count=batch.row_count)

    def check_source_name_registered(self, batch: ExtractorBatch) -> ValidationResult:
        """ERROR if batch.source_name is not registered in SOURCE_ARTIFACT_DECLARATIONS."""
        name = "check_source_name_registered"
        artifacts = get_source_artifacts(batch.source_name)
        if artifacts:
            return self._pass(name, batch.source_name,
                              f"Source '{batch.source_name}' is registered")
        return self._fail(name, batch.source_name, ValidationSeverity.ERROR,
                          f"Source '{batch.source_name}' has no artifact declarations",
                          source_name=batch.source_name)

    def check_inclusion_mode_consistent(self, batch: ExtractorBatch) -> ValidationResult:
        """ERROR if batch.inclusion_mode does not match the declared inclusion_mode."""
        name = "check_inclusion_mode_consistent"
        artifacts = get_source_artifacts(batch.source_name)
        if not artifacts:
            return self._pass(name, batch.source_name,
                              "No declarations to compare inclusion mode against")

        declared_modes = {a.inclusion_mode for a in artifacts}
        if batch.inclusion_mode in declared_modes:
            return self._pass(name, batch.source_name,
                              "Inclusion mode is consistent with declarations")
        return self._fail(name, batch.source_name, ValidationSeverity.ERROR,
                          f"Batch inclusion_mode '{batch.inclusion_mode}' "
                          f"not in declared modes {sorted(declared_modes)}",
                          batch_mode=batch.inclusion_mode,
                          declared_modes=sorted(declared_modes))

    def check_row_types_consistent(self, batch: ExtractorBatch) -> ValidationResult:
        """ERROR if rows are not all the same type, or type lacks from_row()."""
        name = "check_row_types_consistent"
        if not batch.rows:
            return self._pass(name, batch.source_name, "No rows to check types on")

        first_type = type(batch.rows[0])
        inconsistent = [i for i, r in enumerate(batch.rows) if type(r) is not first_type]
        if inconsistent:
            return self._fail(name, batch.source_name, ValidationSeverity.ERROR,
                              f"Rows have mixed types; expected all {first_type.__name__}",
                              expected_type=first_type.__name__,
                              inconsistent_indices=inconsistent[:10])

        if not hasattr(first_type, "from_row"):
            return self._fail(name, batch.source_name, ValidationSeverity.ERROR,
                              f"Row type {first_type.__name__} has no from_row() classmethod",
                              row_type=first_type.__name__)

        return self._pass(name, batch.source_name,
                          f"All {batch.row_count} rows are {first_type.__name__}")

    def check_required_fields_present(
        self,
        batch: ExtractorBatch,
        required_fields: tuple[str, ...],
    ) -> list[ValidationResult]:
        """ERROR for each required field where any rows have None. One result per field."""
        results: list[ValidationResult] = []
        name = "check_required_fields_present"

        if not required_fields:
            return results

        for field_name in required_fields:
            null_count = sum(
                1 for row in batch.rows
                if getattr(row, field_name, None) is None
            )
            if null_count == 0:
                results.append(self._pass(
                    f"{name}.{field_name}", batch.source_name,
                    f"Required field '{field_name}' is present on all rows",
                ))
            else:
                results.append(self._fail(
                    f"{name}.{field_name}", batch.source_name,
                    ValidationSeverity.ERROR,
                    f"Required field '{field_name}' is None on {null_count} rows",
                    field_name=field_name,
                    null_count=null_count,
                    total_rows=batch.row_count,
                ))

        return results

    def check_no_pii_in_batch(self, batch: ExtractorBatch) -> ValidationResult:
        """CRITICAL if any row's fields contain a PII field name as a key."""
        name = "check_no_pii_in_batch"
        if not batch.rows:
            return self._pass(name, batch.source_name, "No rows to check for PII")

        first_row = batch.rows[0]
        if dataclasses.is_dataclass(first_row):
            field_names = {f.name for f in dataclasses.fields(first_row)}
        else:
            field_names = set(vars(first_row).keys())

        violations = sorted(field_names & PII_PROPERTY_NAMES)
        if not violations:
            return self._pass(name, batch.source_name, "No PII field names found in row schema")
        return self._fail(name, batch.source_name, ValidationSeverity.CRITICAL,
                          f"Row schema contains PII field names: {violations}",
                          pii_fields=violations,
                          source_name=batch.source_name)

    def check_freshness_field_present(self, batch: ExtractorBatch) -> ValidationResult:
        """WARNING if freshness field is declared but all rows have None for it."""
        name = "check_freshness_field_present"
        if not batch.rows:
            return self._pass(name, batch.source_name, "No rows to check freshness on")

        row_type = type(batch.rows[0])
        schema_module = sys.modules.get(row_type.__module__)
        freshness_field: str | None = getattr(schema_module, "FRESHNESS_FIELD", None)

        if freshness_field is None:
            return self._pass(name, batch.source_name,
                              "No FRESHNESS_FIELD declared for this source")

        all_null = all(getattr(row, freshness_field, None) is None for row in batch.rows)
        if not all_null:
            return self._pass(name, batch.source_name,
                              f"Freshness field '{freshness_field}' has values",
                              freshness_field=freshness_field)
        return self._warn(name, batch.source_name,
                          f"All rows have None for freshness field '{freshness_field}'",
                          freshness_field=freshness_field,
                          row_count=batch.row_count)

    def check_row_count_reasonable(
        self,
        batch: ExtractorBatch,
        max_expected: int = 500_000,
    ) -> ValidationResult:
        """WARNING if row count exceeds max_expected."""
        name = "check_row_count_reasonable"
        if batch.row_count <= max_expected:
            return self._pass(name, batch.source_name,
                              f"Row count {batch.row_count} is within limit",
                              row_count=batch.row_count)
        return self._warn(name, batch.source_name,
                          f"Row count {batch.row_count} exceeds max_expected {max_expected}; "
                          "may indicate a missing incremental filter",
                          row_count=batch.row_count,
                          max_expected=max_expected)


def validate_batch(batch: ExtractorBatch, run_id: str) -> list[ValidationResult]:
    """Module-level convenience: construct SourceValidator and run validate()."""
    return SourceValidator(run_id).validate(batch)