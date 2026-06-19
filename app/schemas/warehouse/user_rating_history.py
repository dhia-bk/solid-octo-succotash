"""
Warehouse schema for fct_user_rating_history.

Source table: fct_user_rating_history
Domain: intelligence
Inclusion mode: GRAPH_CORE — direct graph node creation
Graph entity: RatingSnapshot
Freshness field: created_at_utc

ELO-style duel rating change events per user. Enables temporal analysis of
user skill progression. Feeds RatingSnapshot nodes and HAS_RATING relationship
(User → RatingSnapshot).

DWH type notes:
    rating_event_id     — VARCHAR(100) in DWH; no declared PK constraint;
                          treated as the stable unique identifier.
    previous_rating,
    new_rating,
    change_amount       — INTEGER in DWH; exposed as float | None (semantic
                          override: ratings are conceptually continuous and
                          will gain decimal precision as the model evolves;
                          matches the float type on UserNode.duel_rating).
    rating_date_key     — INTEGER in DWH (yyyymmdd partition key); exposed
                          as str | None — partition label, not a quantity.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.core.constants import GRAPH_CORE, RATING_SNAPSHOT
from app.core.ids import normalize_nullable_string_id, normalize_string_id
from app.core.time import warehouse_value_to_utc_datetime

# ── Module-level constants ────────────────────────────────────────────────────

SOURCE_NAME: str = "fct_user_rating_history"
INCLUSION_MODE: str = GRAPH_CORE
PRIMARY_KEYS: tuple[str, ...] = ("rating_event_id",)
FRESHNESS_FIELD: str | None = "created_at_utc"
GRAPH_ENTITY_MAPPINGS: tuple[str, ...] = (RATING_SNAPSHOT,)


# ── Row shape ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class UserRatingHistoryRow:
    """
    Typed row shape for fct_user_rating_history.

    previous_rating, new_rating, and change_amount are stored as INTEGER
    in the DWH but exposed as float | None to align with the continuous
    ELO rating model used on User nodes (duel_rating is float there).
    rating_date_key is exposed as str | None (partition label).
    """

    rating_event_id: str
    user_id: str | None
    duel_id: str | None
    previous_rating: float | None
    new_rating: float | None
    change_amount: float | None
    reason: str | None
    created_at_utc: datetime | None
    rating_date_key: str | None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> UserRatingHistoryRow:
        """Normalize a raw warehouse row into a typed UserRatingHistoryRow."""
        return cls(
            rating_event_id=normalize_string_id(row["rating_event_id"], field_name="rating_event_id"),
            user_id=normalize_nullable_string_id(row.get("user_id"), field_name="user_id"),
            duel_id=normalize_nullable_string_id(row.get("duel_id"), field_name="duel_id"),
            previous_rating=float(row["previous_rating"]) if row.get("previous_rating") is not None else None,
            new_rating=float(row["new_rating"]) if row.get("new_rating") is not None else None,
            change_amount=float(row["change_amount"]) if row.get("change_amount") is not None else None,
            reason=row.get("reason"),
            created_at_utc=warehouse_value_to_utc_datetime(row.get("created_at_utc")),
            rating_date_key=str(row["rating_date_key"]) if row.get("rating_date_key") is not None else None,
        )
