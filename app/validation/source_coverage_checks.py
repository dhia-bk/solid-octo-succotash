"""
Source inventory completeness validation.

Ensures every declared source has a transformer, extractor, and mapping spec.
Pure registry inspection — no database clients needed.
Can be run at startup to catch mapping layer regressions.
"""

from __future__ import annotations

from app.mappings.endpoint_resolution import ENDPOINT_SPECS
from app.mappings.merge_keys import MERGE_KEY_SPECS
from app.mappings.property_ownership import PROPERTY_OWNERSHIP_SPECS
from app.mappings.source_to_graph import SOURCE_ARTIFACT_DECLARATIONS
from app.validation.base import BaseValidator, ValidationResult, ValidationSeverity

# Multi-source nodes that must have full property ownership coverage declared.
_MULTI_SOURCE_LABELS: frozenset[str] = frozenset(
    {"User", "Team", "Question", "PartnerReward"}
)


class SourceCoverageValidator(BaseValidator):
    """Validates completeness of source inventory and mapping layer declarations."""

    def validate(self, *args, **kwargs) -> list[ValidationResult]:  # type: ignore[override]
        raise NotImplementedError(
            "Use run_all_coverage_checks() or individual check methods."
        )

    # ── transformer / extractor coverage ──────────────────────────────────────

    def check_all_sources_have_transformers(
        self, transformer_registry: dict[str, type],
    ) -> list[ValidationResult]:
        """ERROR for each emitting source with no transformer class registered."""
        name = "check_all_sources_have_transformers"
        results: list[ValidationResult] = []
        for decl in SOURCE_ARTIFACT_DECLARATIONS:
            if not decl.emits_records:
                continue
            if decl.source_name in transformer_registry:
                results.append(self._pass(
                    name, decl.source_name,
                    f"Transformer registered for '{decl.source_name}'",
                ))
            else:
                results.append(self._fail(
                    name, decl.source_name, ValidationSeverity.ERROR,
                    f"No transformer class registered for emitting source '{decl.source_name}'",
                    source_name=decl.source_name,
                    artifact_kind=decl.artifact_kind,
                    target=decl.target_label_or_rel,
                ))
        return results

    def check_all_sources_have_extractors(
        self, extractor_registry: dict[str, type],
    ) -> list[ValidationResult]:
        """ERROR for each source with no extractor class registered."""
        name = "check_all_sources_have_extractors"
        results: list[ValidationResult] = []
        seen: set[str] = set()
        for decl in SOURCE_ARTIFACT_DECLARATIONS:
            if decl.source_name in seen:
                continue
            seen.add(decl.source_name)
            if decl.source_name in extractor_registry:
                results.append(self._pass(
                    name, decl.source_name,
                    f"Extractor registered for '{decl.source_name}'",
                ))
            else:
                results.append(self._fail(
                    name, decl.source_name, ValidationSeverity.ERROR,
                    f"No extractor class registered for source '{decl.source_name}'",
                    source_name=decl.source_name,
                ))
        return results

    # ── merge key coverage ─────────────────────────────────────────────────────

    def check_all_sources_have_merge_keys(self) -> list[ValidationResult]:
        """ERROR for each emitting source with no MergeKeySpec entry."""
        name = "check_all_sources_have_merge_keys"
        merge_key_sources: frozenset[str] = frozenset(
            spec.source_name for spec in MERGE_KEY_SPECS
        )
        results: list[ValidationResult] = []
        for decl in SOURCE_ARTIFACT_DECLARATIONS:
            if not decl.emits_records:
                continue
            if decl.source_name in merge_key_sources:
                results.append(self._pass(
                    name, decl.source_name,
                    f"MergeKeySpec present for '{decl.source_name}'",
                ))
            else:
                results.append(self._fail(
                    name, decl.source_name, ValidationSeverity.ERROR,
                    f"No MergeKeySpec found for emitting source '{decl.source_name}'",
                    source_name=decl.source_name,
                    artifact_kind=decl.artifact_kind,
                ))
        return results

    # ── endpoint spec coverage ─────────────────────────────────────────────────

    def check_all_relationship_endpoints_declared(self) -> list[ValidationResult]:
        """ERROR for each relationship-emitting source missing start/end EndpointSpecs."""
        name = "check_all_relationship_endpoints_declared"
        results: list[ValidationResult] = []

        for decl in SOURCE_ARTIFACT_DECLARATIONS:
            if not decl.emits_records or decl.artifact_kind != "relationship":
                continue
            rel_type = decl.target_label_or_rel
            source_name = decl.source_name

            has_start = any(
                k[0] == rel_type and k[1] == "start" and k[2] == source_name
                for k in ENDPOINT_SPECS
            )
            has_end = any(
                k[0] == rel_type and k[1] == "end" and k[2] == source_name
                for k in ENDPOINT_SPECS
            )

            if has_start and has_end:
                results.append(self._pass(
                    name, source_name,
                    f"Start and end EndpointSpecs declared for ({rel_type}, {source_name})",
                ))
            else:
                missing = []
                if not has_start:
                    missing.append("start")
                if not has_end:
                    missing.append("end")
                results.append(self._fail(
                    name, source_name, ValidationSeverity.ERROR,
                    f"Missing endpoint spec(s) {missing} "
                    f"for relationship '{rel_type}' from '{source_name}'",
                    source_name=source_name,
                    rel_type=rel_type,
                    missing_endpoints=missing,
                ))

        return results

    # ── orphan checks ──────────────────────────────────────────────────────────

    def check_no_orphaned_merge_key_specs(self) -> list[ValidationResult]:
        """WARNING for each MergeKeySpec whose source_name has no artifact declaration."""
        name = "check_no_orphaned_merge_key_specs"
        declared_sources: frozenset[str] = frozenset(
            d.source_name for d in SOURCE_ARTIFACT_DECLARATIONS
        )
        results: list[ValidationResult] = []
        for spec in MERGE_KEY_SPECS:
            if spec.source_name in declared_sources:
                results.append(self._pass(
                    name, spec.source_name,
                    f"MergeKeySpec source '{spec.source_name}' is in declarations",
                ))
            else:
                results.append(self._warn(
                    name, spec.source_name,
                    f"Orphaned MergeKeySpec: '{spec.source_name}' has no artifact declaration",
                    source_name=spec.source_name,
                    target_name=spec.target_name,
                ))
        return results

    def check_no_orphaned_endpoint_specs(self) -> list[ValidationResult]:
        """WARNING for each EndpointSpec whose (rel_type, source_name) has no declaration."""
        name = "check_no_orphaned_endpoint_specs"
        declared_rel_sources: frozenset[tuple[str, str]] = frozenset(
            (d.target_label_or_rel, d.source_name)
            for d in SOURCE_ARTIFACT_DECLARATIONS
            if d.artifact_kind == "relationship" and d.emits_records
        )
        results: list[ValidationResult] = []
        seen: set[tuple[str, str]] = set()
        for (rel_type, endpoint_name, source_name), _ in ENDPOINT_SPECS.items():
            key = (rel_type, source_name)
            if key in seen:
                continue
            seen.add(key)
            if key in declared_rel_sources:
                results.append(self._pass(
                    name, source_name,
                    f"EndpointSpec ({rel_type}, {source_name}) matches a declaration",
                ))
            else:
                results.append(self._warn(
                    name, source_name,
                    f"Orphaned EndpointSpec: ({rel_type}, {source_name}) "
                    "has no relationship declaration",
                    rel_type=rel_type,
                    source_name=source_name,
                ))
        return results

    # ── property ownership coverage ────────────────────────────────────────────

    def check_property_ownership_coverage(self) -> list[ValidationResult]:
        """WARNING for each multi-source node label with undeclared properties."""
        name = "check_property_ownership_coverage"
        owned_pairs: frozenset[tuple[str, str]] = frozenset(
            (spec.target_label_or_rel, spec.property_name)
            for spec in PROPERTY_OWNERSHIP_SPECS
        )
        results: list[ValidationResult] = []

        for label in _MULTI_SOURCE_LABELS:
            label_owned = {pair[1] for pair in owned_pairs if pair[0] == label}
            if label_owned:
                results.append(self._pass(
                    name, label,
                    f"{len(label_owned)} property ownership spec(s) declared for '{label}'",
                    property_count=len(label_owned),
                ))
            else:
                results.append(self._warn(
                    name, label,
                    f"No PropertyOwnershipSpec entries found for multi-source label '{label}'",
                    label=label,
                ))

        return results


def run_all_coverage_checks(
    transformer_registry: dict[str, type],
    extractor_registry: dict[str, type],
) -> list[ValidationResult]:
    """Convenience: run all coverage checks and return a flat list of results."""
    import uuid
    validator = SourceCoverageValidator(run_id=f"coverage-{uuid.uuid4().hex[:8]}")
    results: list[ValidationResult] = []
    results.extend(validator.check_all_sources_have_transformers(transformer_registry))
    results.extend(validator.check_all_sources_have_extractors(extractor_registry))
    results.extend(validator.check_all_sources_have_merge_keys())
    results.extend(validator.check_all_relationship_endpoints_declared())
    results.extend(validator.check_no_orphaned_merge_key_specs())
    results.extend(validator.check_no_orphaned_endpoint_specs())
    results.extend(validator.check_property_ownership_coverage())
    return results