"""
Warehouse schema for fct_topics.

Source table: fct_topics
Domain: intelligence
Inclusion mode: GRAPH_CORE — direct graph node creation
Graph entity: Topic
Freshness field: processed_at

ML-derived topic labels per content item and user. Feeds Topic nodes and
the DISCUSSED relationship (User → Topic).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.core.constants import GRAPH_CORE, TOPIC
from app.core.ids import normalize_nullable_string_id, normalize_string_id
from app.core.time import warehouse_value_to_utc_datetime

# ── Module-level constants ────────────────────────────────────────────────────

SOURCE_NAME: str = "fct_topics"
INCLUSION_MODE: str = GRAPH_CORE
PRIMARY_KEYS: tuple[str, ...] = ("id",)
FRESHNESS_FIELD: str | None = "processed_at"
GRAPH_ENTITY_MAPPINGS: tuple[str, ...] = (TOPIC,)


# ── Row shape ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class TopicsRow:
    """
    Typed row shape for fct_topics.

    id is an INTEGER PK; kept as int at this layer.
    item_id and user_id are VARCHAR in the DWH; str | None.
    """

    id: int
    source_type: str | None
    item_id: str | None
    user_id: str | None
    topic_label: str | None
    reasoning: str | None
    processed_at: datetime | None
    model_provider: str | None
    model_version: str | None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> TopicsRow:
        """Normalize a raw warehouse row into a typed TopicsRow."""
        return cls(
            id=int(normalize_string_id(row["id"], field_name="id")),
            source_type=row.get("source_type"),
            item_id=normalize_nullable_string_id(row.get("item_id"), field_name="item_id"),
            user_id=normalize_nullable_string_id(row.get("user_id"), field_name="user_id"),
            topic_label=row.get("topic_label"),
            reasoning=row.get("reasoning"),
            processed_at=warehouse_value_to_utc_datetime(row.get("processed_at")),
            model_provider=row.get("model_provider"),
            model_version=row.get("model_version"),
        )
