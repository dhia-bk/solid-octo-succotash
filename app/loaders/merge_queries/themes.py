"""
Merge queries for league themes.
Source(s): dim_private_league_themes
"""

from __future__ import annotations

from app.loaders.merge_queries.base import (
    build_node_merge_query,
    build_relationship_merge_query,
)


def get_league_theme_merge_query(
    source_name: str = "dim_private_league_themes",
) -> str:
    """Return Cypher MERGE query for LeagueTheme from source_name."""
    return build_node_merge_query(
        label="LeagueTheme",
        merge_key_field="id",
        write_once_fields=[],
        mutable_fields=[
            "theme_name",
            "theme_palette",
            "background_image_url",
            "is_default",
        ],
    )


def get_has_theme_merge_query(source_name: str = "dim_private_league_themes") -> str:
    """Return Cypher MERGE query for HAS_THEME (PrivateLeague→LeagueTheme) from source_name."""
    return build_relationship_merge_query(
        rel_type="HAS_THEME",
        start_label="PrivateLeague",
        end_label="LeagueTheme",
        start_merge_field="id",
        end_merge_field="id",
        rel_merge_fields=["theme_id"],
        rel_property_fields=["applied_at"],
    )
