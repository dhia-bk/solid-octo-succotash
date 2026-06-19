"""
Warehouse schema for fct_awards_and_achievements.

Source table: fct_awards_and_achievements
Domain: economy
Inclusion mode: GRAPH_CORE — direct graph node creation and relationship
Graph entity: Achievement node + ACHIEVED relationship (User → Achievement)
Freshness field: earned_at_utc

Achievement and award events. Feeds both Achievement node creation and the
ACHIEVED relationship (User → Achievement).

DWH type notes:
    award_id      — VARCHAR(255) in DWH; str (spec suggested int).
    user_id       — VARCHAR(255) in DWH; str | None.
    earned_at_utc — VARCHAR(255) in DWH (stored as ISO string, not a native
                    DATETIME column); normalized via warehouse_value_to_utc_datetime
                    which handles string input safely.
    earned_date_key — INTEGER partition key; str | None.
    reward_amount — DOUBLE in DWH; float | None (spec suggested int).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.core.constants import ACHIEVED, ACHIEVEMENT, GRAPH_CORE
from app.core.ids import normalize_nullable_string_id, normalize_string_id
from app.core.time import warehouse_value_to_utc_datetime

# ── Module-level constants ────────────────────────────────────────────────────

SOURCE_NAME: str = "fct_awards_and_achievements"
INCLUSION_MODE: str = GRAPH_CORE
PRIMARY_KEYS: tuple[str, ...] = ("award_id",)
FRESHNESS_FIELD: str | None = "earned_at_utc"
GRAPH_ENTITY_MAPPINGS: tuple[str, ...] = (ACHIEVEMENT, ACHIEVED)


# ── Row shape ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class AwardsAndAchievementsRow:
    """
    Typed row shape for fct_awards_and_achievements.

    award_id is VARCHAR(255) in the DWH; stored as str.
    user_id is VARCHAR(255) in the DWH; str | None.

    earned_at_utc is VARCHAR(255) in the DWH (ISO string, not a native
    DATETIME column). warehouse_value_to_utc_datetime handles string input
    safely.

    earned_date_key is an INTEGER partition key; str | None.
    reward_amount is DOUBLE in the DWH; float | None.
    """

    award_id: str
    achievement_type: str | None
    badge_id: int | None
    badge_name: str | None
    earned_at_utc: datetime | None
    earned_date_key: str | None
    private_league_id: int | None
    reward_amount: float | None
    trophy_description: str | None
    trophy_id: int | None
    trophy_name: str | None
    user_id: str | None
    created_at: datetime | None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> AwardsAndAchievementsRow:
        """Normalize a raw warehouse row into a typed AwardsAndAchievementsRow."""
        return cls(
            award_id=normalize_string_id(row["award_id"], field_name="award_id"),
            achievement_type=row.get("achievement_type"),
            badge_id=int(row["badge_id"]) if row.get("badge_id") is not None else None,
            badge_name=row.get("badge_name"),
            earned_at_utc=warehouse_value_to_utc_datetime(row.get("earned_at_utc")),
            earned_date_key=str(row["earned_date_key"]) if row.get("earned_date_key") is not None else None,
            private_league_id=int(row["private_league_id"]) if row.get("private_league_id") is not None else None,
            reward_amount=float(row["reward_amount"]) if row.get("reward_amount") is not None else None,
            trophy_description=row.get("trophy_description"),
            trophy_id=int(row["trophy_id"]) if row.get("trophy_id") is not None else None,
            trophy_name=row.get("trophy_name"),
            user_id=normalize_nullable_string_id(row.get("user_id"), field_name="user_id"),
            created_at=warehouse_value_to_utc_datetime(row.get("created_at")),
        )
