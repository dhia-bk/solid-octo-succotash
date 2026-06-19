"""
Warehouse schema for dim_comments.

Source table: dim_comments
Domain: social
Inclusion mode: GRAPH_CORE — direct graph node creation
Graph entity: Comment
Freshness field: created_at_utc

Comments on posts. Feeds COMMENTED (User → Comment) and REPLIES_TO
(Comment → Comment) relationships. parent_comment_id enables thread nesting.

DWH type notes:
    comment_id        — VARCHAR(100) in DWH; stored as str (not int).
    post_id           — VARCHAR(100) in DWH; str | None.
    parent_comment_id — VARCHAR(100) in DWH; str | None (nullable for
                        top-level comments that have no parent).
    user_id           — VARCHAR(100) in DWH; str | None.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.core.constants import COMMENT, GRAPH_CORE
from app.core.ids import normalize_nullable_string_id, normalize_string_id
from app.core.time import warehouse_value_to_utc_datetime

# ── Module-level constants ────────────────────────────────────────────────────

SOURCE_NAME: str = "dim_comments"
INCLUSION_MODE: str = GRAPH_CORE
PRIMARY_KEYS: tuple[str, ...] = ("comment_id",)
FRESHNESS_FIELD: str | None = "created_at_utc"
GRAPH_ENTITY_MAPPINGS: tuple[str, ...] = (COMMENT,)


# ── Row shape ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class CommentsRow:
    """
    Typed row shape for dim_comments.

    comment_id, post_id, and parent_comment_id are VARCHAR in the DWH;
    stored as str / str | None.
    """

    comment_id: str
    user_id: str | None
    post_id: str | None
    content: str | None
    created_at_utc: datetime | None
    like_count: int | None
    parent_comment_id: str | None
    clap_count: int | None
    fire_count: int | None
    football_count: int | None
    thumbs_down_count: int | None
    thumbs_up_count: int | None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> CommentsRow:
        """Normalize a raw warehouse row into a typed CommentsRow."""
        return cls(
            comment_id=normalize_string_id(row["comment_id"], field_name="comment_id"),
            user_id=normalize_nullable_string_id(row.get("user_id"), field_name="user_id"),
            post_id=normalize_nullable_string_id(row.get("post_id"), field_name="post_id"),
            content=row.get("content"),
            created_at_utc=warehouse_value_to_utc_datetime(row.get("created_at_utc")),
            like_count=int(row["like_count"]) if row.get("like_count") is not None else None,
            parent_comment_id=normalize_nullable_string_id(row.get("parent_comment_id"), field_name="parent_comment_id"),
            clap_count=int(row["clap_count"]) if row.get("clap_count") is not None else None,
            fire_count=int(row["fire_count"]) if row.get("fire_count") is not None else None,
            football_count=int(row["football_count"]) if row.get("football_count") is not None else None,
            thumbs_down_count=int(row["thumbs_down_count"]) if row.get("thumbs_down_count") is not None else None,
            thumbs_up_count=int(row["thumbs_up_count"]) if row.get("thumbs_up_count") is not None else None,
        )
