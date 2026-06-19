"""
Warehouse schema for fct_content_engagement_daily.

Source table: fct_content_engagement_daily
Domain: ops
Inclusion mode: SERVING_ONLY — feeds content engagement dashboards
Graph entity: none
Freshness field: metric_date

Daily content engagement rollup per content item. No declared PK; engagement_id
treated as the stable de facto key. Feeds dashboards, not graph.

DWH type notes:
    engagement_id  — VARCHAR(100); no declared PK; str.
    content_id     — INTEGER in DWH (not str as spec suggested); int | None.
    metric_date    — DATE column; str | None (date-only; no tz coercion).
    metric_date_key — INTEGER partition key; str | None.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.core.constants import SERVING_ONLY
from app.core.ids import normalize_nullable_string_id, normalize_string_id

# ── Module-level constants ────────────────────────────────────────────────────

SOURCE_NAME: str = "fct_content_engagement_daily"
INCLUSION_MODE: str = SERVING_ONLY
PRIMARY_KEYS: tuple[str, ...] = ("engagement_id",)
FRESHNESS_FIELD: str | None = "metric_date"
GRAPH_ENTITY_MAPPINGS: tuple[str, ...] = ()


# ── Row shape ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ContentEngagementDailyRow:
    """
    Typed row shape for fct_content_engagement_daily.

    content_id is INTEGER in the DWH; int | None (spec suggested str —
    DWH wins here).
    metric_date is a DATE column; str | None (date-only label).
    metric_date_key is an INTEGER partition key; str | None.
    """

    engagement_id: str
    content_type: str | None
    content_id: int | None
    metric_date: str | None
    metric_date_key: str | None
    likes_today: int | None
    comments_today: int | None
    tag_count: int | None
    team_mention_count: int | None
    league_mention_count: int | None
    total_engagement_today: int | None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> ContentEngagementDailyRow:
        """Normalize a raw warehouse row into a typed ContentEngagementDailyRow."""
        return cls(
            engagement_id=normalize_string_id(row["engagement_id"], field_name="engagement_id"),
            content_type=row.get("content_type"),
            content_id=int(row["content_id"]) if row.get("content_id") is not None else None,
            metric_date=str(row["metric_date"]) if row.get("metric_date") is not None else None,
            metric_date_key=str(row["metric_date_key"]) if row.get("metric_date_key") is not None else None,
            likes_today=int(row["likes_today"]) if row.get("likes_today") is not None else None,
            comments_today=int(row["comments_today"]) if row.get("comments_today") is not None else None,
            tag_count=int(row["tag_count"]) if row.get("tag_count") is not None else None,
            team_mention_count=int(row["team_mention_count"]) if row.get("team_mention_count") is not None else None,
            league_mention_count=int(row["league_mention_count"]) if row.get("league_mention_count") is not None else None,
            total_engagement_today=int(row["total_engagement_today"]) if row.get("total_engagement_today") is not None else None,
        )
