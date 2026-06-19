"""
Coverage report builder for the Project Pulse Knowledge Graph source inventory.

This file builds structured summaries over the source registry. It does not
validate entries (that is inclusion_rules.py's job), connect to any database,
or read YAML. It only reads the registry and produces structured output.

Typical callers:
    scripts/run_source_inventory_audit.py
    app/source_inventory/coverage_report.py (CLI smoke test at bottom)
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from app.core.constants import (
    EXCLUDED,
    FEATURE_SOURCE,
    GRAPH_CORE,
    GRAPH_ENRICHMENT,
    SERVING_ONLY,
    SOURCE_INCLUSION_CATEGORIES,
)
from app.core.time import format_log_timestamp
from app.source_inventory.registry import SourceEntry


# Coverage summary dataclass


@dataclass(frozen=True)
class CoverageSummary:
    """
    Structured snapshot of source registry coverage.

    Attributes:
        total_sources: Total number of registered source entries.
        by_inclusion_mode: Count of sources per inclusion mode.
        by_domain: Count of sources per domain.
        sources_without_freshness_field: Source names with no freshness_field.
            Includes static dimensions (expected) and any accidental omissions.
        sources_without_graph_mappings: Source names with no graph entity
            mappings. Covers SERVING_ONLY, FEATURE_SOURCE, and EXCLUDED entries
            by design, plus any GRAPH_CORE/ENRICHMENT entries missing mappings.
        graph_core_count: Number of GRAPH_CORE sources.
        enrichment_count: Number of GRAPH_ENRICHMENT sources.
        serving_only_count: Number of SERVING_ONLY sources.
        feature_source_count: Number of FEATURE_SOURCE sources.
        excluded_count: Number of EXCLUDED sources.
        generated_at: UTC ISO timestamp of report generation.
    """

    total_sources: int
    by_inclusion_mode: dict[str, int]
    by_domain: dict[str, int]
    sources_without_freshness_field: list[str]
    sources_without_graph_mappings: list[str]
    graph_core_count: int
    enrichment_count: int
    serving_only_count: int
    feature_source_count: int
    excluded_count: int
    generated_at: str


# Report builder


def build_coverage_report(registry: dict[str, SourceEntry]) -> CoverageSummary:
    """
    Build a CoverageSummary from a source registry mapping.

    Args:
        registry: Mapping of source_name to SourceEntry.

    Returns:
        Populated CoverageSummary instance.
    """
    by_mode: dict[str, int] = defaultdict(int)
    by_domain: dict[str, int] = defaultdict(int)
    no_freshness: list[str] = []
    no_mappings: list[str] = []

    for source_name, entry in registry.items():
        by_mode[entry.inclusion_mode] += 1
        by_domain[entry.domain] += 1

        if entry.freshness_field is None:
            no_freshness.append(source_name)

        if not entry.graph_entity_mappings:
            no_mappings.append(source_name)

    return CoverageSummary(
        total_sources=len(registry),
        by_inclusion_mode=dict(sorted(by_mode.items())),
        by_domain=dict(sorted(by_domain.items())),
        sources_without_freshness_field=sorted(no_freshness),
        sources_without_graph_mappings=sorted(no_mappings),
        graph_core_count=by_mode.get(GRAPH_CORE, 0),
        enrichment_count=by_mode.get(GRAPH_ENRICHMENT, 0),
        serving_only_count=by_mode.get(SERVING_ONLY, 0),
        feature_source_count=by_mode.get(FEATURE_SOURCE, 0),
        excluded_count=by_mode.get(EXCLUDED, 0),
        generated_at=format_log_timestamp(),
    )


# Domain breakdown helper


def get_domain_breakdown(
    registry: dict[str, SourceEntry],
) -> dict[str, dict[str, int]]:
    """
    Return a nested count of sources grouped by domain then inclusion mode.

    Example output:
        {
            "identity":   {"graph_core": 3, "graph_enrichment": 1},
            "social":     {"graph_core": 9, "graph_enrichment": 1},
            "ops":        {"graph_core": 1, "serving_only": 3, "feature_source": 2},
        }

    Args:
        registry: Mapping of source_name to SourceEntry.

    Returns:
        Dict of {domain: {inclusion_mode: count}}, both levels sorted
        alphabetically.
    """
    breakdown: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    for entry in registry.values():
        breakdown[entry.domain][entry.inclusion_mode] += 1

    return {
        domain: dict(sorted(modes.items()))
        for domain, modes in sorted(breakdown.items())
    }


# Text summary helper

# Column widths for the formatted tables
_COL_NAME = 34
_COL_COUNT = 6
_SEPARATOR = "-" * (_COL_NAME + _COL_COUNT + 3)


def _mode_label(mode: str) -> str:
    """
    Return a short, readable label for an inclusion mode constant.
    """
    labels = {
        GRAPH_CORE: "graph_core",
        GRAPH_ENRICHMENT: "graph_enrichment",
        SERVING_ONLY: "serving_only",
        FEATURE_SOURCE: "feature_source",
        EXCLUDED: "excluded",
    }
    return labels.get(mode, mode)


def format_coverage_report(summary: CoverageSummary) -> str:
    """
    Format a CoverageSummary as a human-readable multiline string.

    Suitable for CLI output (run_source_inventory_audit.py) or structured
    log emission.

    Args:
        summary: CoverageSummary produced by build_coverage_report().

    Returns:
        Formatted report string.
    """
    lines: list[str] = []

    def section(title: str) -> None:
        lines.append("")
        lines.append(title)
        lines.append("=" * len(title))

    def row(label: str, count: int) -> None:
        lines.append(f"  {label:<{_COL_NAME}} {count:>{_COL_COUNT}}")

    def divider() -> None:
        lines.append(f"  {_SEPARATOR}")

    # Header
    lines.append("Source Registry Coverage Report")
    lines.append(f"Generated at: {summary.generated_at}")
    lines.append(f"Total sources registered: {summary.total_sources}")

    # Inclusion mode breakdown
    section("By Inclusion Mode")
    for mode in SOURCE_INCLUSION_CATEGORIES:
        count = summary.by_inclusion_mode.get(mode, 0)
        row(_mode_label(mode), count)
    divider()
    row("TOTAL", summary.total_sources)

    # Domain breakdown
    section("By Domain")
    for domain, count in sorted(summary.by_domain.items(), key=lambda x: -x[1]):
        row(domain, count)

    # Sources without a freshness field
    section("Sources Without Freshness Field")
    if summary.sources_without_freshness_field:
        lines.append(
            "  (static dimensions use full refresh — verify these are intentional)"
        )
        for name in summary.sources_without_freshness_field:
            lines.append(f"    • {name}")
    else:
        lines.append("  None — all sources have a freshness field.")

    # Sources without graph mappings
    section("Sources Without Graph Entity Mappings")
    lines.append(
        "  (serving_only / feature_source / excluded entries are expected here)"
    )
    if summary.sources_without_graph_mappings:
        for name in summary.sources_without_graph_mappings:
            lines.append(f"    • {name}")
    else:
        lines.append("  None — all sources have graph entity mappings.")

    lines.append("")
    return "\n".join(lines)