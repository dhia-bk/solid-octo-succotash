"""
Sports pipeline — leagues, teams, fixtures.

FK dependency order: leagues before fixtures (IN_LEAGUE requires League nodes),
teams before fixtures (HOME_TEAM/AWAY_TEAM require Team nodes),
dim_teams before dim_teams_enhanced (enrichment targets existing Team nodes).
"""

from __future__ import annotations

from app.core.constants import SPORTS_PIPELINE
from app.pipelines.base import BasePipeline


class SportsPipeline(BasePipeline):
    """
    Loads sports domain nodes: League, Team, Match.

    Order enforces FK integrity: catalog nodes before relationship sources.
    """

    pipeline_name = SPORTS_PIPELINE
    sources = (
        "dim_leagues",          # League nodes — before fixtures (IN_LEAGUE)
        "dim_teams",            # Team nodes (core identity)
        "dim_teams_enhanced",   # Team enrichment — after dim_teams
        "dim_fixtures",         # Match nodes + HOME_TEAM + AWAY_TEAM + IN_LEAGUE
    )
