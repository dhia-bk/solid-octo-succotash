"""
Warehouse schema for dim_posts.

Source table: dim_posts
Domain: social
Inclusion mode: GRAPH_CORE — direct graph node creation
Graph entity: Post
Freshness field: published_at_utc

User-generated posts. Feeds POSTED (User → Post) and HAS_TAG (Post → Tag)
relationships, and is an input to topic and sentiment analysis.

DWH type note:
    post_id       — VARCHAR(100) in DWH; stored as str (not int as the spec
                    initially suggested). Consistent with how post_id is
                    referenced as a FK in dim_comments.
    author_user_id — VARCHAR(100) in DWH; str.
    is_active     — TINYINT 0/1 flag.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.core.constants import GRAPH_CORE, POST
from app.core.ids import normalize_nullable_string_id, normalize_string_id
from app.core.time import warehouse_value_to_utc_datetime

# ── Module-level constants ────────────────────────────────────────────────────

SOURCE_NAME: str = "dim_posts"
INCLUSION_MODE: str = GRAPH_CORE
PRIMARY_KEYS: tuple[str, ...] = ("post_id",)
FRESHNESS_FIELD: str | None = "published_at_utc"
GRAPH_ENTITY_MAPPINGS: tuple[str, ...] = (POST,)


# ── Row shape ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class PostsRow:
    """
    Typed row shape for dim_posts.

    TINYINT fields (0/1 integers, not booleans in the DWH):
        is_active

    post_id is VARCHAR(100) in the DWH; stored as str.
    """

    post_id: str
    author_user_id: str | None
    title: str | None
    description: str | None
    content: str | None
    url: str | None
    image: str | None
    video: str | None
    published_at_utc: datetime | None
    like_count: int | None
    view_count: int | None
    is_active: int | None
    clap_count: int | None
    fire_count: int | None
    football_count: int | None
    thumbs_down_count: int | None
    thumbs_up_count: int | None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> PostsRow:
        """Normalize a raw warehouse row into a typed PostsRow."""
        return cls(
            post_id=normalize_string_id(row["post_id"], field_name="post_id"),
            author_user_id=normalize_nullable_string_id(row.get("author_user_id"), field_name="author_user_id"),
            title=row.get("title"),
            description=row.get("description"),
            content=row.get("content"),
            url=row.get("url"),
            image=row.get("image"),
            video=row.get("video"),
            published_at_utc=warehouse_value_to_utc_datetime(row.get("published_at_utc")),
            like_count=int(row["like_count"]) if row.get("like_count") is not None else None,
            view_count=int(row["view_count"]) if row.get("view_count") is not None else None,
            is_active=int(row["is_active"]) if row.get("is_active") is not None else None,
            clap_count=int(row["clap_count"]) if row.get("clap_count") is not None else None,
            fire_count=int(row["fire_count"]) if row.get("fire_count") is not None else None,
            football_count=int(row["football_count"]) if row.get("football_count") is not None else None,
            thumbs_down_count=int(row["thumbs_down_count"]) if row.get("thumbs_down_count") is not None else None,
            thumbs_up_count=int(row["thumbs_up_count"]) if row.get("thumbs_up_count") is not None else None,
        )
