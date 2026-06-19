"""
Inclusion rules engine for Project Pulse Knowledge Graph source inventory.

This file defines the validation rules applied to every SourceEntry in the
registry. It does not store entries, load config, connect to any database,
or read YAML.

Responsibilities:
- validate that each source has a correct and internally consistent
  inclusion assignment
- check that required structural fields are present for each mode
- ensure graph-core and enrichment sources have entity mappings
- ensure serving-only and feature sources carry no graph mappings
- detect excluded sources that lack an explanatory note

Usage:
    from app.source_inventory.registry import _REGISTRY
    from app.source_inventory.inclusion_rules import assert_registry_valid

    assert_registry_valid(_REGISTRY)

Done when:
- all 65 current registry entries pass with zero errors
- a deliberately broken entry raises SourceInclusionError in tests
"""

from __future__ import annotations

from app.core.constants import (
    EXCLUDED,
    FEATURE_SOURCE,
    GRAPH_CORE,
    GRAPH_ENRICHMENT,
    SERVING_ONLY,
    SOURCE_INCLUSION_CATEGORIES,
)
from app.core.exceptions import SourceInclusionError
from app.core.logging import get_logger
from app.source_inventory.registry import SourceEntry

logger = get_logger(__name__)


# Internal constants

# Keywords that qualify a GRAPH_CORE entry as intentionally static when it
# has no freshness_field. The notes field must contain at least one of these
# (case-insensitive) for the missing freshness_field to be accepted.
_STATIC_DIM_KEYWORDS: frozenset[str] = frozenset(
    {
        "static",
        "full refresh",
        "numeric watermark",
        "no timestamp",
    }
)


# Per-mode rule validators

def _check_has_primary_keys(entry: SourceEntry) -> list[str]:
    """
    Return an error if the entry has no primary keys defined.
    """
    if not entry.primary_keys:
        return [
            f"[{entry.inclusion_mode}] '{entry.source_name}' has no primary_keys defined; "
            "at least one key field is required"
        ]
    return []


def _check_has_graph_mappings(entry: SourceEntry) -> list[str]:
    """
    Return an error if the entry has no graph entity mappings.
    """
    if not entry.graph_entity_mappings:
        return [
            f"[{entry.inclusion_mode}] '{entry.source_name}' has no graph_entity_mappings; "
            "at least one node label or relationship type is required"
        ]
    return []


def _check_has_no_graph_mappings(entry: SourceEntry) -> list[str]:
    """
    Return an error if the entry incorrectly declares graph entity mappings.
    """
    if entry.graph_entity_mappings:
        return [
            f"[{entry.inclusion_mode}] '{entry.source_name}' must not have graph_entity_mappings "
            f"but declares: {list(entry.graph_entity_mappings)}"
        ]
    return []


def _check_freshness_or_static(entry: SourceEntry) -> list[str]:
    """
    Return an error if a GRAPH_CORE entry has neither a freshness_field nor
    an explicit static-dimension acknowledgment in its notes.

    GRAPH_CORE entries without a freshness_field are valid only when the notes
    field clearly states that the table is a static dimension or uses full
    refresh. This prevents silent omissions from the registry.
    """
    if entry.freshness_field is not None:
        return []

    notes_lower = entry.notes.lower()
    has_static_signal = any(kw in notes_lower for kw in _STATIC_DIM_KEYWORDS)

    if not has_static_signal:
        return [
            f"[{entry.inclusion_mode}] '{entry.source_name}' has no freshness_field and "
            "no static-dimension acknowledgment in its notes. Either set a freshness_field "
            "for incremental extraction, or add 'static', 'full refresh', 'numeric watermark', "
            "or 'no timestamp' to the notes to indicate intentional full-refresh behavior."
        ]
    return []


def _check_has_freshness_field(entry: SourceEntry) -> list[str]:
    """
    Return an error if the entry has no freshness field at all.

    Used for modes where a freshness field is unconditionally required
    (SERVING_ONLY) regardless of notes.
    """
    if not entry.freshness_field:
        return [
            f"[{entry.inclusion_mode}] '{entry.source_name}' has no freshness_field; "
            "a date or timestamp column is required for incremental refresh"
        ]
    return []


def _check_has_exclusion_note(entry: SourceEntry) -> list[str]:
    """
    Return an error if an EXCLUDED entry has no explanatory note.
    """
    if not entry.notes or not entry.notes.strip():
        return [
            f"[{entry.inclusion_mode}] '{entry.source_name}' is marked EXCLUDED but has "
            "no notes explaining the exclusion decision"
        ]
    return []


def _check_valid_inclusion_mode(entry: SourceEntry) -> list[str]:
    """
    Return an error if the inclusion mode is not one of the known categories.
    """
    if entry.inclusion_mode not in SOURCE_INCLUSION_CATEGORIES:
        return [
            f"'{entry.source_name}' has unknown inclusion_mode '{entry.inclusion_mode}'; "
            f"must be one of {list(SOURCE_INCLUSION_CATEGORIES)}"
        ]
    return []


def _check_source_name_not_blank(entry: SourceEntry) -> list[str]:
    """
    Return an error if source_name is blank.
    """
    if not entry.source_name or not entry.source_name.strip():
        return ["Source entry has a blank source_name"]
    return []


def _check_domain_not_blank(entry: SourceEntry) -> list[str]:
    """
    Return an error if domain is blank.
    """
    if not entry.domain or not entry.domain.strip():
        return [
            f"'{entry.source_name}' has a blank domain; "
            "every source must be assigned to a named domain"
        ]
    return []


# Mode-specific validators


def _validate_graph_core(entry: SourceEntry) -> list[str]:
    """
    Validate a GRAPH_CORE entry.

    Rules:
    - must have at least one primary key
    - must have at least one graph entity mapping
    - must have a freshness_field OR notes must acknowledge static/full-refresh
    """
    errors: list[str] = []
    errors.extend(_check_has_primary_keys(entry))
    errors.extend(_check_has_graph_mappings(entry))
    errors.extend(_check_freshness_or_static(entry))
    return errors


def _validate_graph_enrichment(entry: SourceEntry) -> list[str]:
    """
    Validate a GRAPH_ENRICHMENT entry.

    Rules:
    - must have at least one graph entity mapping (identifies the target node
      type this source enriches)
    - must have at least one primary key (provides a stable reference key for
      the enrichment join; name matching against the target entity key is
      enforced at the transformer level, not here)

    Note: freshness_field is not required for GRAPH_ENRICHMENT entries.
    Static enrichment dimensions (e.g. dim_private_league_themes) are valid
    without a freshness_field. The extractor decides whether to use incremental
    or full-refresh mode based on the entry's freshness_field value.
    """
    errors: list[str] = []
    errors.extend(_check_has_primary_keys(entry))
    errors.extend(_check_has_graph_mappings(entry))
    return errors


def _validate_serving_only(entry: SourceEntry) -> list[str]:
    """
    Validate a SERVING_ONLY entry.

    Rules:
    - must have at least one primary key or date key (ensures the serving table
      is addressable for upserts)
    - must NOT have graph entity mappings (serving tables never feed graph nodes
      or relationships directly)
    - must have a freshness_field (serving tables must support incremental
      materialization refresh)
    """
    errors: list[str] = []
    errors.extend(_check_has_primary_keys(entry))
    errors.extend(_check_has_no_graph_mappings(entry))
    errors.extend(_check_has_freshness_field(entry))
    return errors


def _validate_feature_source(entry: SourceEntry) -> list[str]:
    """
    Validate a FEATURE_SOURCE entry.

    Rules:
    - must have at least one primary key (feature computation requires a
      stable row identifier)
    - must NOT have graph entity mappings (feature sources feed ML pipelines,
      not the graph directly)
    """
    errors: list[str] = []
    errors.extend(_check_has_primary_keys(entry))
    errors.extend(_check_has_no_graph_mappings(entry))
    return errors


def _validate_excluded(entry: SourceEntry) -> list[str]:
    """
    Validate an EXCLUDED entry.

    Rules:
    - must have a non-empty notes field explaining why the source is excluded
    - no structural requirements on keys or mappings (the source is not used)
    """
    return _check_has_exclusion_note(entry)


# Dispatch table

_MODE_VALIDATORS: dict[str, callable] = {
    GRAPH_CORE: _validate_graph_core,
    GRAPH_ENRICHMENT: _validate_graph_enrichment,
    SERVING_ONLY: _validate_serving_only,
    FEATURE_SOURCE: _validate_feature_source,
    EXCLUDED: _validate_excluded,
}


# Public validation interface


def validate_source_entry(entry: SourceEntry) -> list[str]:
    """
    Validate a single SourceEntry against the rules for its inclusion mode.

    Args:
        entry: Source entry to validate.

    Returns:
        List of error message strings. Empty list means the entry is valid.
    """
    errors: list[str] = []

    # Universal checks applied to every entry regardless of mode
    errors.extend(_check_source_name_not_blank(entry))
    errors.extend(_check_domain_not_blank(entry))
    errors.extend(_check_valid_inclusion_mode(entry))

    # If the mode itself is invalid we skip mode-specific validation to avoid
    # confusing cascading errors
    if errors:
        return errors

    validator = _MODE_VALIDATORS[entry.inclusion_mode]
    errors.extend(validator(entry))

    return errors


def validate_registry(
    registry: dict[str, SourceEntry],
) -> dict[str, list[str]]:
    """
    Validate every entry in a registry mapping.

    Args:
        registry: Mapping of source_name to SourceEntry (typically _REGISTRY
            from app.source_inventory.registry).

    Returns:
        Dict of {source_name: [error strings]} for every source that has at
        least one violation. Sources with no violations are omitted from the
        result. An empty dict means the entire registry is valid.
    """
    violations: dict[str, list[str]] = {}

    for source_name, entry in registry.items():
        entry_errors = validate_source_entry(entry)
        if entry_errors:
            violations[source_name] = entry_errors

    return violations


def assert_registry_valid(registry: dict[str, SourceEntry]) -> None:
    """
    Assert that every entry in the registry satisfies its inclusion rules.

    Logs the full violation report before raising so the error is visible in
    structured logs even if the exception is caught upstream.

    Args:
        registry: Mapping of source_name to SourceEntry.

    Raises:
        SourceInclusionError: If any entry fails validation, containing the
            number of violations and the list of affected sources.
    """
    violations = validate_registry(registry)

    if not violations:
        logger.info(
            "Source registry validation passed",
            extra={"total_sources": len(registry)},
        )
        return

    total_errors = sum(len(errs) for errs in violations.values())

    for source_name, errors in sorted(violations.items()):
        for error in errors:
            logger.error(
                "Source registry validation error",
                extra={
                    "source_name": source_name,
                    "error": error,
                },
            )

    raise SourceInclusionError(
        "Source registry validation failed",
        violated_sources=sorted(violations.keys()),
        total_sources=len(registry),
        total_violations=total_errors,
    )


# Convenience helpers for targeted queries


def get_sources_missing_freshness(
    registry: dict[str, SourceEntry],
) -> list[str]:
    """
    Return source names that have no freshness_field and are not statically
    acknowledged.

    Useful for coverage reporting and incremental sync planning. This does not
    imply those sources are invalid — EXCLUDED and GRAPH_ENRICHMENT entries
    without a freshness field may be intentional.

    Args:
        registry: Source registry mapping.

    Returns:
        Sorted list of source names without a freshness field.
    """
    return sorted(
        name
        for name, entry in registry.items()
        if entry.freshness_field is None
    )


def get_sources_without_graph_mappings(
    registry: dict[str, SourceEntry],
) -> list[str]:
    """
    Return source names that declare no graph entity mappings.

    Covers SERVING_ONLY, FEATURE_SOURCE, and EXCLUDED entries by design.
    Useful for identifying sources that are intentionally excluded from graph
    construction.

    Args:
        registry: Source registry mapping.

    Returns:
        Sorted list of source names with empty graph_entity_mappings.
    """
    return sorted(
        name
        for name, entry in registry.items()
        if not entry.graph_entity_mappings
    )


def get_graph_core_sources_without_freshness(
    registry: dict[str, SourceEntry],
) -> list[str]:
    """
    Return GRAPH_CORE source names that have no freshness_field.

    These are intentional static dimensions (full refresh). Useful for
    checkpoint configuration: these sources should use the
    CHECKPOINT_STRATEGY_FULL_REFRESH strategy.

    Args:
        registry: Source registry mapping.

    Returns:
        Sorted list of GRAPH_CORE source names that use full refresh.
    """
    return sorted(
        name
        for name, entry in registry.items()
        if entry.inclusion_mode == GRAPH_CORE and entry.freshness_field is None
    )


def summarize_violations(violations: dict[str, list[str]]) -> str:
    """
    Format a violations dict into a human-readable multiline summary string.

    Args:
        violations: Output of validate_registry().

    Returns:
        Formatted string suitable for CLI output or log emission.
    """
    if not violations:
        return "Source registry validation: all entries are valid."

    lines: list[str] = [
        f"Source registry validation: {len(violations)} source(s) with violations.",
        "",
    ]
    for source_name in sorted(violations):
        lines.append(f"  {source_name}:")
        for error in violations[source_name]:
            lines.append(f"    - {error}")
        lines.append("")

    return "\n".join(lines).rstrip()