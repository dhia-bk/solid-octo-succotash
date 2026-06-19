"""
Warehouse schema for dim_tags.

Source table: dim_tags
Domain: engagement
Inclusion mode: GRAPH_CORE — direct graph node creation
Graph entity: Tag
Freshness field: last_used_at_utc

Tag catalog with trending signals. Feeds Tag nodes and HAS_TAG relationships
(Post → Tag, News → Tag, AIArticle → Tag).

DWH type notes:
    tag_id         — INTEGER PK; int.
    team_id        — INTEGER; int | None (carries a team reference for sport tags).
    league_id      — INTEGER; int | None.
    trending_score — DECIMAL(10,2); float | None.
    is_trending    — TINYINT 0/1.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.core.constants import GRAPH_CORE, TAG
from app.core.ids import normalize_string_id
from app.core.time import warehouse_value_to_utc_datetime

# ── Module-level constants ────────────────────────────────────────────────────

SOURCE_NAME: str = "dim_tags"
INCLUSION_MODE: str = GRAPH_CORE
PRIMARY_KEYS: tuple[str, ...] = ("tag_id",)
FRESHNESS_FIELD: str | None = "last_used_at_utc"
GRAPH_ENTITY_MAPPINGS: tuple[str, ...] = (TAG,)


# ── Row shape ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class TagsRow:
    """
    Typed row shape for dim_tags.

    TINYINT fields (0/1 integers, not booleans in the DWH):
        is_trending

    trending_score is DECIMAL(10,2) in the DWH; float | None.
    """

    tag_id: int
    tag_name: str | None
    tag_url: str | None
    post_usage_count: int | None
    news_usage_count: int | None
    last_used_at_utc: datetime | None
    team_id: int | None
    league_id: int | None
    is_trending: int | None
    trending_score: float | None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> TagsRow:
        """Normalize a raw warehouse row into a typed TagsRow."""
        return cls(
            tag_id=int(normalize_string_id(row["tag_id"], field_name="tag_id")),
            tag_name=row.get("tag_name"),
            tag_url=row.get("tag_url"),
            post_usage_count=int(row["post_usage_count"]) if row.get("post_usage_count") is not None else None,
            news_usage_count=int(row["news_usage_count"]) if row.get("news_usage_count") is not None else None,
            last_used_at_utc=warehouse_value_to_utc_datetime(row.get("last_used_at_utc")),
            team_id=int(row["team_id"]) if row.get("team_id") is not None else None,
            league_id=int(row["league_id"]) if row.get("league_id") is not None else None,
            is_trending=int(row["is_trending"]) if row.get("is_trending") is not None else None,
            trending_score=float(row["trending_score"]) if row.get("trending_score") is not None else None,
        )
