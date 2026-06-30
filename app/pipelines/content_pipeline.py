"""
Content pipeline — tags, news, AI articles, private league themes.

dim_tags first so HAS_TAG relationships in other content sources resolve.
Requires identity_pipeline (User) and sports_pipeline (Match for GENERATED_FOR).
"""

from __future__ import annotations

from app.core.constants import CONTENT_PIPELINE
from app.pipelines.base import BasePipeline


class ContentPipeline(BasePipeline):
    """
    Loads content domain nodes: Tag, News, AIArticle, LeagueTheme.
    """

    pipeline_name = CONTENT_PIPELINE
    sources = (
        "dim_tags",                     # Tag catalog nodes — before HAS_TAG rels
        "dim_news",                     # News nodes
"dim_private_league_themes",    # LeagueTheme nodes + HAS_THEME rels
    )
