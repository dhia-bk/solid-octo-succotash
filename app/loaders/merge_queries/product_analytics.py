"""
Merge queries for product analytics.
Source(s): fct_product_events (not yet mapped)
"""

from __future__ import annotations


def get_product_event_merge_query(source_name: str = "fct_product_events") -> str:
    """Placeholder — product analytics merge queries not yet mapped."""
    raise NotImplementedError(
        f"Product analytics merge query not implemented for source: {source_name}"
    )
