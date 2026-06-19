"""
Warehouse schema for dim_avatars.

Source table: dim_avatars
Domain: identity
Inclusion mode: GRAPH_CORE — direct graph node creation
Graph entity: Avatar
Freshness field: None (static dimension — full refresh on every run)

Avatar catalog. Changes infrequently; no timestamp column in DWH.
Feeds EQUIPPED relationship (User → Avatar) and Avatar node creation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.core.constants import AVATAR, GRAPH_CORE
from app.core.ids import normalize_string_id

# ── Module-level constants ────────────────────────────────────────────────────

SOURCE_NAME: str = "dim_avatars"
INCLUSION_MODE: str = GRAPH_CORE
PRIMARY_KEYS: tuple[str, ...] = ("avatar_id",)
FRESHNESS_FIELD: str | None = None
GRAPH_ENTITY_MAPPINGS: tuple[str, ...] = (AVATAR,)


# ── Row shape ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class AvatarsRow:
    """
    Typed row shape for dim_avatars.

    avatar_id is an INTEGER PK in the DWH; kept as int at this layer.
    adoption_rate is a DOUBLE in the DWH.
    """

    avatar_id: int
    avatar_name: str | None
    avatar_image: str | None
    avatar_description: str | None
    users_unlocked: int | None
    adoption_rate: float | None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> AvatarsRow:
        """Normalize a raw warehouse row into a typed AvatarsRow."""
        return cls(
            avatar_id=int(normalize_string_id(row["avatar_id"], field_name="avatar_id")),
            avatar_name=row.get("avatar_name"),
            avatar_image=row.get("avatar_image"),
            avatar_description=row.get("avatar_description"),
            users_unlocked=int(row["users_unlocked"]) if row.get("users_unlocked") is not None else None,
            adoption_rate=float(row["adoption_rate"]) if row.get("adoption_rate") is not None else None,
        )
