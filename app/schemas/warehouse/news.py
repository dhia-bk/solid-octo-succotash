"""
Warehouse schema for dim_news.

Source table: dim_news
Domain: ai_communication
Inclusion mode: GRAPH_CORE — direct graph node creation
Graph entity: News
Freshness field: published_at_utc

Editorial news dimension. Feeds News nodes and HAS_TAG (News → Tag)
relationship. news_id is an INTEGER PK in the DWH; aligns with spec.

DWH type notes:
    news_id       — INTEGER PK; kept as int.
    published_at_utc — TIMESTAMP in DWH.
    is_active     — TINYINT 0/1.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.core.constants import GRAPH_CORE, NEWS
from app.core.ids import normalize_string_id
from app.core.time import warehouse_value_to_utc_datetime

# ── Module-level constants ────────────────────────────────────────────────────

SOURCE_NAME: str = "dim_news"
INCLUSION_MODE: str = GRAPH_CORE
PRIMARY_KEYS: tuple[str, ...] = ("news_id",)
FRESHNESS_FIELD: str | None = "published_at_utc"
GRAPH_ENTITY_MAPPINGS: tuple[str, ...] = (NEWS,)


# ── Row shape ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class NewsRow:
    """
    Typed row shape for dim_news.

    TINYINT fields (0/1 integers, not booleans in the DWH):
        is_active

    news_id is an INTEGER PK; stored as int.
    """

    news_id: int
    title: str | None
    content: str | None
    published_at_utc: datetime | None
    author: str | None
    image: str | None
    url: str | None
    is_active: int | None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> NewsRow:
        """Normalize a raw warehouse row into a typed NewsRow."""
        return cls(
            news_id=int(normalize_string_id(row["news_id"], field_name="news_id")),
            title=row.get("title"),
            content=row.get("content"),
            published_at_utc=warehouse_value_to_utc_datetime(row.get("published_at_utc")),
            author=row.get("author"),
            image=row.get("image"),
            url=row.get("url"),
            is_active=int(row["is_active"]) if row.get("is_active") is not None else None,
        )
