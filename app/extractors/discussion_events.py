"""
Extractor for the fct_discussion_events warehouse source.

Purpose:
- Extract user participation events from fct_discussion_events, including
  user, discussion linkage, event type, timestamp, content preview, and
  engagement counts.
- Incremental strategy using event_at_utc as the watermark.
- Return typed DiscussionEventsRow instances wrapped in ExtractorBatch.

Source characteristics:
    fct_discussion_events is an append-oriented event log. Each row records
    a single user action within a fixture or prediction discussion thread
    (e.g. join, post, react). Events are not updated after initial write;
    event_at_utc is the authoritative event timestamp.

    A row can reference either a fixture discussion (discussion_id) or a
    prediction discussion (prediction_discussion_id); exactly one of the two
    will be non-NULL per row. Both fields must be preserved so the transformer
    can route JOINED_DISCUSSION edges to the correct parent thread type.

    like_count is included as a per-event engagement counter and, like
    reaction counts on posts and comments, can increment after the event's
    original event_at_utc. This is a minor metric tradeoff; the event
    identity and participation signal (event_type, user_id, discussion linkage)
    are immutable after initial write.

Design rules:
- event_id is VARCHAR(255) in the DWH; preserved as str. No SQL CAST applied.
- discussion_id and prediction_discussion_id are both INTEGER and mutually
  exclusive per row. Both must be present in every extracted row; the
  transformer decides which FK to follow, not the extractor.
- event_date_key is an INTEGER partition label in the DWH; stored as
  str | None in DiscussionEventsRow. No numeric arithmetic applied.
- content_preview may contain user-generated text; extracted faithfully —
  length enforcement is a loader concern.
- No graph logic, canonicalization, or enrichment is applied here.

Source schema:
- Source table  : fct_discussion_events
- Inclusion mode: GRAPH_CORE
- Graph entity  : JOINED_DISCUSSION relationship (User → Discussion)
- Freshness field: event_at_utc
"""

from __future__ import annotations

from app.contracts.warehouse_rows import WarehouseRow
from app.extractors.base import BaseExtractor
from app.schemas.warehouse.discussion_events import (
    FRESHNESS_FIELD,
    INCLUSION_MODE,
    PRIMARY_KEYS,
    SOURCE_NAME,
    DiscussionEventsRow,
)


class DiscussionEventsExtractor(BaseExtractor):
    """
    Extractor for fct_discussion_events.

    Incremental strategy:
    - watermark field: event_at_utc
    - ordering: event_at_utc, event_id

    Dual discussion linkage:
    - Each row carries either discussion_id (fixture thread) or
      prediction_discussion_id (prediction thread); the non-relevant FK
      will be NULL. Both columns are always selected; routing belongs to
      the transformer layer.

    Append-oriented semantics:
    - Events are written once and not updated after initial insert.
      Incremental extraction by event_at_utc is therefore complete and
      correct with no mutation window required.
    """

    source_name: str = SOURCE_NAME
    schema_row_class: type[WarehouseRow] = DiscussionEventsRow
    inclusion_mode: str = INCLUSION_MODE
    freshness_field: str | None = FRESHNESS_FIELD     # event_at_utc
    primary_key_fields: tuple[str, ...] = PRIMARY_KEYS
    default_chunk_size: int = 5000
    supports_incremental: bool = True

    # ── Source column contract ────────────────────────────────────────────────

    def get_source_columns(self) -> tuple[str, ...]:
        """
        Return the explicit ordered source columns for fct_discussion_events.

        These columns must stay aligned with DiscussionEventsRow.from_row().
        Adding or removing a column here requires a matching change in
        the schema row dataclass.

        Dual linkage note:
            discussion_id and prediction_discussion_id are mutually exclusive
            per row (one is non-NULL, the other NULL). Both must be selected;
            the transformer determines which FK to follow for edge routing.

        Partition label note:
            event_date_key is an INTEGER in the DWH but is a partition label,
            not a numeric quantity. DiscussionEventsRow stores it as str | None.
        """
        return (
            "event_id",
            "user_id",
            "discussion_id",              # fixture thread FK — NULL when prediction thread
            "prediction_discussion_id",   # prediction thread FK — NULL when fixture thread
            "event_type",
            "event_at_utc",
            "event_date_key",
            "content_preview",
            "like_count",
        )

    # ── Query construction ────────────────────────────────────────────────────

    def build_base_query(self) -> str:
        """
        Return the base SELECT for fct_discussion_events without incremental
        filtering.

        The incremental clause (WHERE event_at_utc > :watermark_value)
        is appended by the base runtime via build_incremental_clause().
        """
        columns = ",\n    ".join(self.get_source_columns())
        return f"""
SELECT
    {columns}
FROM {self.source_name}
""".strip()

    def build_incremental_clause(self, watermark_value: str | None) -> str:
        """
        Build the incremental filter using event_at_utc.

        Uses strict greater-than semantics so watermark advancement remains
        monotonic across runs. No clause is emitted on first run (watermark
        is None), triggering a full-table bootstrap load.
        """
        if not self.supports_incremental or not self.freshness_field:
            return ""

        if not watermark_value:
            return ""

        return f"\nWHERE {self.freshness_field} > :watermark_value"

    def build_order_by_clause(self) -> str:
        """
        Return stable deterministic ordering for fct_discussion_events.

        event_at_utc first — aligns with watermark advancement and clusters
        output by participation time, matching the natural downstream
        consumption pattern for discussion event ingestion.

        event_id second — VARCHAR PK; breaks ties within the same event
        timestamp bucket deterministically.
        """
        return "\nORDER BY event_at_utc, event_id"

    def build_pagination_clause(self, limit: int, offset: int) -> str:
        """
        Return LIMIT/OFFSET pagination clause.
        """
        return "\nLIMIT %(limit)s OFFSET %(offset)s"