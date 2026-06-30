"""
Extractor for the fct_heatmap_events warehouse source.

Purpose:
- Extract raw UX click/scroll event rows from fct_heatmap_events, including
  user and session identity, event timestamp, partition date key, page and
  element context, event type, pixel coordinates, viewport dimensions, scroll
  depth, time on page, and device/browser context.
- Incremental strategy using event_timestamp_utc as the watermark.
- Return typed HeatmapEventsRow instances wrapped in ExtractorBatch.

High-volume source:
    fct_heatmap_events is a raw UX telemetry event stream. It is expected to
    be significantly higher volume than any other source in this pipeline.
    Chunk size, pagination, and incremental filtering are tuned accordingly:
    - default_chunk_size is set to 5000 to reduce round-trips on large
      incremental windows.
    - The incremental watermark (event_timestamp_utc) is critical — running
      a full-table bootstrap on this source may require an explicit backfill
      strategy rather than a single extraction run.

Non-graph source:
    fct_heatmap_events is FEATURE_SOURCE — it feeds the behaviour model
    feature computation pipeline only and emits no graph nodes or edges. The
    extractor obeys the same BaseExtractor contract as graph-emitting sources;
    INCLUSION_MODE carries the routing signal that downstream consumers use
    to distinguish feature-pipeline rows from graph rows.

No declared PK:
    fct_heatmap_events has no declared PK constraint in the DWH.
    heatmap_event_id is VARCHAR(50) and is treated as the stable de facto key.
    The extractor does not deduplicate rows — that is a feature-pipeline
    concern if duplicates are detected.

Watermark field — event_timestamp_utc:
    event_timestamp_utc is the correct incremental field because
    fct_heatmap_events is an immutable append-only event stream. New events
    always carry an event_timestamp_utc beyond the previous watermark;
    incremental runs therefore capture all newly recorded telemetry events
    without rescanning historical rows.

    Volume implication: on a busy day, the number of rows with
    event_timestamp_utc beyond the watermark may be very large. Callers
    should prefer extract_in_chunks() over extract_all() for this source.

Nullable user and session fields:
    user_id is NULL for anonymous (unauthenticated) events. session_id is
    NULL for events recorded outside a tracked session. Both are extracted
    faithfully as NULL; the behaviour model pipeline must handle anonymous
    events as a distinct population from authenticated events.

DWH type overrides:
    x_coordinate, y_coordinate — INTEGER in DWH (pixel coords, not float
        as spec suggested); extracted as int | None.
    scroll_depth_percent — INTEGER in DWH (0-100 integer percent, not float
        as spec suggested); extracted as int | None.
    event_date_key — INTEGER partition key; coerced to str | None.

Design rules:
- heatmap_event_id is VARCHAR(50) with no declared PK constraint; treated as
  the stable de facto key. Deduplication is a downstream concern.
- No graph logic, feature engineering, or coordinate normalization here.
- element_text and page_url may be large free-text fields; extracted
  faithfully — field-length enforcement is a loader concern.

Source schema:
- Source table  : fct_heatmap_events
- Inclusion mode: FEATURE_SOURCE (non-graph)
- Graph entity  : none
- Freshness field: event_timestamp_utc
- Declared PK   : none (heatmap_event_id treated as stable de facto key)
"""

from __future__ import annotations

from app.contracts.warehouse_rows import WarehouseRow
from app.extractors.base import BaseExtractor
from app.schemas.warehouse.heatmap_events import (
    FRESHNESS_FIELD,
    INCLUSION_MODE,
    PRIMARY_KEYS,
    SOURCE_NAME,
    HeatmapEventsRow,
)


class HeatmapEventsExtractor(BaseExtractor):
    """
    Extractor for fct_heatmap_events.

    Incremental strategy:
    - watermark field: event_timestamp_utc
    - ordering: event_timestamp_utc, heatmap_event_id

    High-volume source:
    - Raw UX telemetry event stream; expected to be the highest-volume source
      in the pipeline. default_chunk_size is set to 5000 to reduce round-trips
      on large incremental windows. Callers should prefer extract_in_chunks()
      over extract_all() for this source.

    Non-graph source:
    - FEATURE_SOURCE inclusion mode; feeds behaviour model feature pipeline
      only. No graph nodes or edges are emitted. BaseExtractor contract is
      obeyed identically to graph-emitting sources.

    Nullable user and session fields:
    - user_id is NULL for anonymous (unauthenticated) events. session_id is
      NULL for events outside a tracked session. Both extracted faithfully;
      the feature pipeline handles anonymous events as a distinct population.

    No declared PK:
    - heatmap_event_id is the de facto stable key. The extractor preserves
      all rows as received; deduplication is a downstream concern.
    """

    source_name: str = SOURCE_NAME
    schema_row_class: type[WarehouseRow] = HeatmapEventsRow
    inclusion_mode: str = INCLUSION_MODE
    freshness_field: str | None = FRESHNESS_FIELD       # event_timestamp_utc
    primary_key_fields: tuple[str, ...] = PRIMARY_KEYS
    default_chunk_size: int = 5000                      # high-volume event stream
    supports_incremental: bool = True

    # ── Source column contract ────────────────────────────────────────────────

    def get_source_columns(self) -> tuple[str, ...]:
        """
        Return the explicit ordered source columns for fct_heatmap_events.

        These columns must stay aligned with HeatmapEventsRow.from_row().
        Adding or removing a column here requires a matching change in
        the schema row dataclass.

        DWH type override notes:
            x_coordinate, y_coordinate — INTEGER in DWH (pixel coordinates,
                not float as spec suggested); coerced to int | None.
            scroll_depth_percent — INTEGER in DWH (0-100 integer percent, not
                float as spec suggested); coerced to int | None.
            event_date_key — INTEGER partition key; coerced to str | None.

        Nullable fields note:
            user_id   — NULL for anonymous (unauthenticated) events.
            session_id — NULL for events outside a tracked session.
            Both preserved as NULL; feature pipeline handles anonymous events
            as a distinct population.

        No-PK note:
            heatmap_event_id is VARCHAR(50) with no declared PK constraint.
            Treated as the stable de facto key; deduplication belongs to
            downstream consumers.
        """
        return (
            "heatmap_event_id",             # VARCHAR(50); de facto stable key; no PK constraint
            "user_id",                      # NULL for anonymous events
            "session_id",                   # NULL for events outside a tracked session
            "event_timestamp_utc",          # extractor watermark field
            "event_date_key",               # INTEGER partition key in DWH
            "page_url",
            "page_section",
            "element_id",
            "element_class",
            "element_text",
            "event_type",
            "x_coordinate",                 # INTEGER in DWH (not float)
            "y_coordinate",                 # INTEGER in DWH (not float)
            "viewport_width",
            "viewport_height",
            "scroll_depth_percent",         # INTEGER in DWH (0-100 percent, not float)
            "time_on_page_seconds",
            "device_type",
            "browser",
        )

    # ── Query construction ────────────────────────────────────────────────────

    def build_base_query(self) -> str:
        """
        Return the base SELECT for fct_heatmap_events without incremental
        filtering.

        The incremental clause
        (WHERE event_timestamp_utc > :watermark_value) is appended by
        the base runtime via build_incremental_clause().

        Note: extract_all() is strongly discouraged for this source due to
        expected row volume. Callers should use extract_in_chunks() with
        the default or a caller-specified chunk_size.
        """
        columns = ",\n    ".join(self.get_source_columns())
        return f"""
SELECT
    {columns}
FROM {self.source_name}
""".strip()

    def build_incremental_clause(self, watermark_value: str | None) -> str:
        """
        Build the incremental filter using event_timestamp_utc.

        Uses strict greater-than semantics so watermark advancement remains
        monotonic across runs. Appropriate for an immutable append-only event
        stream where events are never mutated post-creation.

        No clause is emitted on first run (watermark is None), triggering a
        full-table bootstrap load. Given the expected volume of this source,
        a full bootstrap should be executed in carefully sized chunks and may
        warrant a dedicated backfill strategy.
        """
        if not self.supports_incremental or not self.freshness_field:
            return ""

        if not watermark_value:
            return ""

        return f"\nWHERE {self.freshness_field} > :watermark_value"

    def build_order_by_clause(self) -> str:
        """
        Return stable deterministic ordering for fct_heatmap_events.

        event_timestamp_utc first — aligns with watermark advancement and
        clusters output chronologically by event time, which is the natural
        ordering for a behaviour model feature pipeline consuming events in
        sequence.

        heatmap_event_id second — VARCHAR(50) de facto stable key; breaks
        ties within the same event_timestamp_utc bucket deterministically.
        Sub-millisecond events sharing an identical timestamp are ordered
        consistently across runs by their stable string key.
        """
        return "\nORDER BY event_timestamp_utc, heatmap_event_id"

    def build_pagination_clause(self, limit: int, offset: int) -> str:
        """
        Return LIMIT/OFFSET pagination clause.
        """
        return "\nLIMIT %(limit)s OFFSET %(offset)s"