"""
Warehouse schema for fct_heatmap_events.

Source table: fct_heatmap_events
Domain: ops
Inclusion mode: FEATURE_SOURCE — feeds behaviour model only
Graph entity: none
Freshness field: event_timestamp_utc

Raw UX click/scroll event stream. Too granular and high-volume for graph
nodes. Feeds the behaviour model feature computation pipeline.

DWH type notes:
    heatmap_event_id — VARCHAR(50); no declared PK; str.
    x_coordinate, y_coordinate — INTEGER in DWH (pixel coords, not float
        as spec suggested); int | None.
    scroll_depth_percent — INTEGER in DWH (0-100 integer percent, not float
        as spec suggested); int | None.
    event_date_key — INTEGER partition key; str | None.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.core.constants import FEATURE_SOURCE
from app.core.ids import normalize_nullable_string_id, normalize_string_id
from app.core.time import warehouse_value_to_utc_datetime

# ── Module-level constants ────────────────────────────────────────────────────

SOURCE_NAME: str = "fct_heatmap_events"
INCLUSION_MODE: str = FEATURE_SOURCE
PRIMARY_KEYS: tuple[str, ...] = ("heatmap_event_id",)
FRESHNESS_FIELD: str | None = "event_timestamp_utc"
GRAPH_ENTITY_MAPPINGS: tuple[str, ...] = ()


# ── Row shape ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class HeatmapEventsRow:
    """
    Typed row shape for fct_heatmap_events.

    heatmap_event_id has no declared PK constraint; treated as the stable
    de facto key.

    x_coordinate, y_coordinate, and scroll_depth_percent are INTEGER in the
    DWH (pixel coordinates and integer percentage); int | None. The spec
    suggested float for these fields — DWH wins.

    event_date_key is an INTEGER partition key; str | None.
    """

    heatmap_event_id: str
    user_id: str | None
    session_id: str | None
    event_timestamp_utc: datetime | None
    event_date_key: str | None
    page_url: str | None
    page_section: str | None
    element_id: str | None
    element_class: str | None
    element_text: str | None
    event_type: str | None
    x_coordinate: int | None
    y_coordinate: int | None
    viewport_width: int | None
    viewport_height: int | None
    scroll_depth_percent: int | None
    time_on_page_seconds: int | None
    device_type: str | None
    browser: str | None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> HeatmapEventsRow:
        """Normalize a raw warehouse row into a typed HeatmapEventsRow."""
        return cls(
            heatmap_event_id=normalize_string_id(row["heatmap_event_id"], field_name="heatmap_event_id"),
            user_id=normalize_nullable_string_id(row.get("user_id"), field_name="user_id"),
            session_id=normalize_nullable_string_id(row.get("session_id"), field_name="session_id"),
            event_timestamp_utc=warehouse_value_to_utc_datetime(row.get("event_timestamp_utc")),
            event_date_key=str(row["event_date_key"]) if row.get("event_date_key") is not None else None,
            page_url=row.get("page_url"),
            page_section=row.get("page_section"),
            element_id=row.get("element_id"),
            element_class=row.get("element_class"),
            element_text=row.get("element_text"),
            event_type=row.get("event_type"),
            x_coordinate=int(row["x_coordinate"]) if row.get("x_coordinate") is not None else None,
            y_coordinate=int(row["y_coordinate"]) if row.get("y_coordinate") is not None else None,
            viewport_width=int(row["viewport_width"]) if row.get("viewport_width") is not None else None,
            viewport_height=int(row["viewport_height"]) if row.get("viewport_height") is not None else None,
            scroll_depth_percent=int(row["scroll_depth_percent"]) if row.get("scroll_depth_percent") is not None else None,
            time_on_page_seconds=int(row["time_on_page_seconds"]) if row.get("time_on_page_seconds") is not None else None,
            device_type=row.get("device_type"),
            browser=row.get("browser"),
        )
