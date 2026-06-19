"""
Warehouse schema for dim_private_league_themes.

Source table: dim_private_league_themes
Domain: social
Inclusion mode: GRAPH_ENRICHMENT — enriches PrivateLeague via LeagueTheme node
Graph entity: LeagueTheme
Freshness field: None (static; full refresh on every run)

Visual theme data for private leagues. Feeds HAS_THEME relationship
(PrivateLeague → LeagueTheme).

DWH type notes:
    theme_id           — INTEGER in DWH; no declared PK constraint. Stored as
                         int | None here. The transformer should use
                         private_league_id as the de facto stable key for
                         graph merge until a proper unique constraint is added.
    private_league_id  — INTEGER; use as fallback stable key when theme_id
                         is null or not unique.
    All color fields and banner_url — TEXT in DWH; str | None.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.core.constants import GRAPH_ENRICHMENT, LEAGUE_THEME

# ── Module-level constants ────────────────────────────────────────────────────

SOURCE_NAME: str = "dim_private_league_themes"
INCLUSION_MODE: str = GRAPH_ENRICHMENT
PRIMARY_KEYS: tuple[str, ...] = ("theme_id",)
FRESHNESS_FIELD: str | None = None
GRAPH_ENTITY_MAPPINGS: tuple[str, ...] = (LEAGUE_THEME,)


# ── Row shape ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class PrivateLeagueThemesRow:
    """
    Typed row shape for dim_private_league_themes.

    theme_id is INTEGER in the DWH but has no declared unique constraint.
    private_league_id is the de facto stable key for graph merge.
    """

    theme_id: int | None
    private_league_id: int | None
    background_color: str | None
    primary_text_color: str | None
    accent_color: str | None
    secondary_text_color: str | None
    card_background_color: str | None
    banner_url: str | None
    default_icon: str | None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> PrivateLeagueThemesRow:
        """Normalize a raw warehouse row into a typed PrivateLeagueThemesRow."""
        return cls(
            theme_id=int(row["theme_id"]) if row.get("theme_id") is not None else None,
            private_league_id=int(row["private_league_id"]) if row.get("private_league_id") is not None else None,
            background_color=row.get("background_color"),
            primary_text_color=row.get("primary_text_color"),
            accent_color=row.get("accent_color"),
            secondary_text_color=row.get("secondary_text_color"),
            card_background_color=row.get("card_background_color"),
            banner_url=row.get("banner_url"),
            default_icon=row.get("default_icon"),
        )
