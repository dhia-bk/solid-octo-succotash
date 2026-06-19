"""
Extractor for the fct_moderation_events warehouse source.

Purpose:
- Extract moderation action event rows from fct_moderation_events, including
  moderator and target user identity, moderation type, event timestamp,
  partition date key, content reference, decision fields, appeal status,
  decision confidence score, and automated flag.
- Incremental strategy using event_at_utc as the watermark.
- Return typed ModerationEventsRow instances wrapped in ExtractorBatch.

Watermark field — event_at_utc:
    event_at_utc is the correct incremental field for this source because
    fct_moderation_events is an immutable event log — moderation events are
    appended, not mutated. New events always carry an event_at_utc beyond the
    previous watermark, ensuring incremental runs capture all newly recorded
    moderation actions without rescanning historical rows.

    Note: appeal_status and moderator_decision may be updated post-creation
    on existing event rows (e.g. when an appeal is reviewed). If such
    mutations do not advance event_at_utc, those updates will not be captured
    incrementally. If post-creation mutations are confirmed in the DWH, a
    secondary updated_at_utc watermark field should be added to the schema.
    This extractor follows event_at_utc as declared in the schema.

Nullable moderator and target fields:
    moderator_user_id is NULL for automated moderation events (where
    automated_flag = 1 and no human moderator acted). target_user_id is NULL
    for events not targeting a specific user. Both are extracted faithfully
    as NULL; the transformer gates MODERATED edge creation on non-NULL values.

Nullable content reference:
    content_id and content_type are NULL for events not tied to specific
    content. Extracted faithfully; the transformer gates content-edge
    creation on non-NULL values.

Design rules:
- event_id is VARCHAR(255) in the DWH (not int as spec suggested); extracted
  as str. Used as the ordering tiebreaker.
- event_date_key is an INTEGER partition key in the DWH; coerced to str | None
  in the row dataclass. Extracted faithfully for downstream partition-aware
  consumers.
- automated_flag is TINYINT 0/1 in the DWH; extracted as int | None, not bool.
- decision_confidence_score is DECIMAL(5,2) in the DWH; coerced to float | None.
- description and reason may be free-text fields of variable length;
  extracted faithfully — field-length enforcement is a loader concern.
- No graph logic, canonicalization, or enrichment is applied here.

Source schema:
- Source table  : fct_moderation_events
- Inclusion mode: GRAPH_CORE
- Graph entity  : ModerationEvent
- Freshness field: event_at_utc
- Declared PK   : event_id (VARCHAR(255))
"""

from __future__ import annotations

from app.contracts.warehouse_rows import WarehouseRow
from app.extractors.base import BaseExtractor
from app.schemas.warehouse.moderation_events import (
    FRESHNESS_FIELD,
    INCLUSION_MODE,
    PRIMARY_KEYS,
    SOURCE_NAME,
    ModerationEventsRow,
)


class ModerationEventsExtractor(BaseExtractor):
    """
    Extractor for fct_moderation_events.

    Incremental strategy:
    - watermark field: event_at_utc
    - ordering: event_at_utc, event_id

    Append-dominant source:
    - fct_moderation_events is an event log; rows are appended, not mutated
      through lifecycle stages. event_at_utc reliably captures all new
      moderation events in incremental runs.

    Appeal and decision mutation caveat:
    - appeal_status and moderator_decision may be updated post-creation. If
      those mutations do not advance event_at_utc, they will be missed
      incrementally. See module docstring for details.

    Nullable moderator and target fields:
    - moderator_user_id is NULL for automated events (automated_flag = 1).
      target_user_id is NULL for non-user-targeted events. Both are extracted
      faithfully; transformer gates edge creation on non-NULL values.

    Nullable content reference:
    - content_id and content_type are NULL for events without content context.
      Extracted faithfully; transformer gates content-edge creation on
      non-NULL values.
    """

    source_name: str = SOURCE_NAME
    schema_row_class: type[WarehouseRow] = ModerationEventsRow
    inclusion_mode: str = INCLUSION_MODE
    freshness_field: str | None = FRESHNESS_FIELD       # event_at_utc
    primary_key_fields: tuple[str, ...] = PRIMARY_KEYS
    default_chunk_size: int = 2000
    supports_incremental: bool = True

    # ── Source column contract ────────────────────────────────────────────────

    def get_source_columns(self) -> tuple[str, ...]:
        """
        Return the explicit ordered source columns for fct_moderation_events.

        These columns must stay aligned with ModerationEventsRow.from_row().
        Adding or removing a column here requires a matching change in
        the schema row dataclass.

        event_id note:
            VARCHAR(255) in the DWH (not int as spec suggested); extracted
            as str. Used as the ordering tiebreaker.

        event_date_key note:
            INTEGER partition key in the DWH; coerced to str | None in the
            row dataclass. Extracted faithfully for partition-aware consumers.

        automated_flag note:
            TINYINT 0/1 in the DWH; coerced to int | None. Not a Python bool.

        decision_confidence_score note:
            DECIMAL(5,2) in the DWH; coerced to float | None.

        Nullable fields note:
            moderator_user_id — NULL for automated moderation events.
            target_user_id    — NULL for events not targeting a specific user.
            content_id        — NULL for events without content context.
            content_type      — NULL for events without content context.
            All preserved as NULL; transformer gates edge creation accordingly.
        """
        return (
            "event_id",                         # VARCHAR(255) in DWH (not int)
            "moderator_user_id",                # NULL for automated events
            "target_user_id",                   # NULL for non-user-targeted events
            "moderation_type",
            "event_at_utc",                     # extractor watermark field
            "event_date_key",                   # INTEGER partition key in DWH
            "reason",
            "description",
            "status",
            "content_id",                       # NULL for events without content context
            "content_type",                     # NULL for events without content context
            "moderator_decision",
            "appeal_status",
            "decision_confidence_score",        # DECIMAL(5,2) in DWH
            "automated_flag",                   # TINYINT 0/1 in DWH (not bool)
        )

    # ── Query construction ────────────────────────────────────────────────────

    def build_base_query(self) -> str:
        """
        Return the base SELECT for fct_moderation_events without incremental
        filtering.

        The incremental clause (WHERE event_at_utc > %(watermark_value)s)
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
        monotonic across runs. Appropriate for an append-dominant event log
        where rows are created but not mutated post-creation in the common
        case.

        No clause is emitted on first run (watermark is None), triggering a
        full-table bootstrap load.
        """
        if not self.supports_incremental or not self.freshness_field:
            return ""

        if not watermark_value:
            return ""

        return f"\nWHERE {self.freshness_field} > %(watermark_value)s"

    def build_order_by_clause(self) -> str:
        """
        Return stable deterministic ordering for fct_moderation_events.

        event_at_utc first — aligns with watermark advancement and clusters
        output chronologically by moderation action time.

        event_id second — VARCHAR(255) de facto PK; breaks ties within the
        same event_at_utc bucket deterministically. String ordering is safe
        here as event_id is a stable identity key, not a numeric or date
        field susceptible to collation edge cases.
        """
        return "\nORDER BY event_at_utc, event_id"

    def build_pagination_clause(self, limit: int, offset: int) -> str:
        """
        Return LIMIT/OFFSET pagination clause.
        """
        return "\nLIMIT %(limit)s OFFSET %(offset)s"