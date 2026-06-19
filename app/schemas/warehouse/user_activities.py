"""
Warehouse schema for fct_user_activities.

Source table: fct_user_activities
Domain: intelligence
Inclusion mode: GRAPH_ENRICHMENT — enrichment signal for activity weight
Graph entity: User (enrichment; does not create a new node type)
Freshness field: activity_at_utc

Fine-grained user activity events (reactions, invites, content interactions).
Used in activity weight computation on User nodes. Not modelled as graph
nodes directly due to volume.

DWH type notes:
    activity_id      — VARCHAR(100) in DWH; str (spec suggested int).
    activity_date_key — INTEGER in DWH (yyyymmdd partition key); exposed
                        as str | None — partition label, not a quantity.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.core.constants import GRAPH_ENRICHMENT, USER
from app.core.ids import normalize_nullable_string_id, normalize_string_id
from app.core.time import warehouse_value_to_utc_datetime

# ── Module-level constants ────────────────────────────────────────────────────

SOURCE_NAME: str = "fct_user_activities"
INCLUSION_MODE: str = GRAPH_ENRICHMENT
PRIMARY_KEYS: tuple[str, ...] = ("activity_id",)
FRESHNESS_FIELD: str | None = "activity_at_utc"
GRAPH_ENTITY_MAPPINGS: tuple[str, ...] = (USER,)


# ── Row shape ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class UserActivitiesRow:
    """
    Typed row shape for fct_user_activities.

    activity_id is VARCHAR(100) in the DWH; stored as str.
    activity_date_key is an INTEGER partition key; exposed as str | None.
    """

    activity_id: str
    user_id: str | None
    activity_type: str | None
    activity_at_utc: datetime | None
    activity_date_key: str | None
    target_id: str | None
    target_type: str | None
    target_owner_user_id: str | None
    reaction_subtype: str | None
    invite_code: str | None
    invite_accepted_at: datetime | None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> UserActivitiesRow:
        """Normalize a raw warehouse row into a typed UserActivitiesRow."""
        return cls(
            activity_id=normalize_string_id(row["activity_id"], field_name="activity_id"),
            user_id=normalize_nullable_string_id(row.get("user_id"), field_name="user_id"),
            activity_type=row.get("activity_type"),
            activity_at_utc=warehouse_value_to_utc_datetime(row.get("activity_at_utc")),
            activity_date_key=str(row["activity_date_key"]) if row.get("activity_date_key") is not None else None,
            target_id=normalize_nullable_string_id(row.get("target_id"), field_name="target_id"),
            target_type=row.get("target_type"),
            target_owner_user_id=normalize_nullable_string_id(row.get("target_owner_user_id"), field_name="target_owner_user_id"),
            reaction_subtype=row.get("reaction_subtype"),
            invite_code=row.get("invite_code"),
            invite_accepted_at=warehouse_value_to_utc_datetime(row.get("invite_accepted_at")),
        )
