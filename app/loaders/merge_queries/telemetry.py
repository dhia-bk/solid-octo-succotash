"""
Merge queries for telemetry / app events.
Source(s): fct_app_events (not yet mapped)
"""

from __future__ import annotations


def get_app_event_merge_query(source_name: str = "fct_app_events") -> str:
    """Placeholder — telemetry merge queries not yet mapped."""
    raise NotImplementedError(
        f"Telemetry merge query not implemented for source: {source_name}"
    )
