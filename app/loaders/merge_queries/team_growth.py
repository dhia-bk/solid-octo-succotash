"""
Merge queries for team growth analytics.
Source(s): fct_team_growth (maps to dim_teams_enhanced enrichment)
"""

from __future__ import annotations

from app.loaders.merge_queries.base import build_enrichment_merge_query


def get_team_growth_enrichment_merge_query(source_name: str = "fct_team_growth") -> str:
    """Return Cypher enrichment query writing team growth stats to Team nodes."""
    return build_enrichment_merge_query(
        label="Team",
        merge_key_field="id",
        enrichment_fields=[],
        write_policy_overwrite=["growth_rate_7d", "growth_rate_30d", "fan_count_delta"],
        write_policy_fill_if_null=[],
    )
