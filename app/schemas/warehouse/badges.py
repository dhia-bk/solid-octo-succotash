"""
Warehouse schema for dim_badges.

Source table: dim_badges
Domain: identity
Inclusion mode: GRAPH_CORE — direct graph node creation
Graph entity: Badge
Freshness field: None (static dimension — full refresh on every run)

Badge catalog. Changes infrequently; no timestamp column in DWH.
Feeds AWARDED relationship (User → Badge) and Badge node creation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.core.constants import BADGE, GRAPH_CORE
from app.core.ids import normalize_string_id

# ── Module-level constants ────────────────────────────────────────────────────

SOURCE_NAME: str = "dim_badges"
INCLUSION_MODE: str = GRAPH_CORE
PRIMARY_KEYS: tuple[str, ...] = ("badge_id",)
FRESHNESS_FIELD: str | None = None
GRAPH_ENTITY_MAPPINGS: tuple[str, ...] = (BADGE,)


# ── Row shape ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class BadgesRow:
    """
    Typed row shape for dim_badges.

    badge_id is an INTEGER PK in the DWH; kept as int at this layer.
    adoption_rate is a DOUBLE in the DWH.
    """

    badge_id: int
    badge_name: str | None
    badge_image: str | None
    badge_description: str | None
    users_awarded: int | None
    adoption_rate: float | None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> BadgesRow:
        """Normalize a raw warehouse row into a typed BadgesRow."""
        return cls(
            badge_id=int(normalize_string_id(row["badge_id"], field_name="badge_id")),
            badge_name=row.get("badge_name"),
            badge_image=row.get("badge_image"),
            badge_description=row.get("badge_description"),
            users_awarded=int(row["users_awarded"]) if row.get("users_awarded") is not None else None,
            adoption_rate=float(row["adoption_rate"]) if row.get("adoption_rate") is not None else None,
        )
