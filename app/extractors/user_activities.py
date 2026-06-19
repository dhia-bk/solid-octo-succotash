"""
Extractor for the fct_user_activities warehouse source.

Purpose:
- Extract fine-grained user activity event rows from fct_user_activities,
  including user identity, activity type, event timestamp, partition date key,
  target entity reference, target owner, reaction subtype, and invite fields.
- Incremental strategy using activity_at_utc as the watermark.
- Return typed UserActivitiesRow instances wrapped in ExtractorBatch.

High-volume event source:
    fct_user_activities captures fine-grained activity events (reactions,
    invites, content interactions) at individual user-action granularity.
    The source is not modelled as graph nodes directly due to volume; rows
    feed activity weight computation on existing User nodes as enrichment
    signal. Chunk size is set conservatively given expected row volume.

Watermark field — activity_at_utc:
    activity_at_utc is the correct incremental field because
    fct_user_activities is an append-only event log — activity events are
    recorded at occurrence and are not mutated post-creation. New events
    always carry an activity_at_utc beyond the previous watermark, ensuring
    incremental runs capture all newly recorded activity events without
    rescanning historical rows.

Nullable target and reaction fields:
    target_id, target_type, and target_owner_user_id are NULL for activities
    that are not directed at a specific content item or user target. Extracted
    faithfully as NULL; the transformer uses target_type to determine which
    entity class the target_id references when non-NULL.

    reaction_subtype is NULL for non-reaction activity types. Extracted
    faithfully; the transformer gates subtype-specific enrichment on
    non-NULL values.

    invite_code and invite_accepted_at are NULL for non-invite activity types.
    Extracted faithfully; the transformer gates invite-specific enrichment
    on non-NULL values.

Design rules:
- activity_id is VARCHAR(100) in the DWH (not int as spec suggested);
  extracted as str. Used as the ordering tiebreaker.
- activity_date_key is an INTEGER partition key (YYYYMMDD) in the DWH;
  coerced to str | None — partition label, not a quantity.
- No graph logic, activity weight computation, or enrichment merging here.

Source schema:
- Source table  : fct_user_activities
- Inclusion mode: GRAPH_ENRICHMENT
- Graph entity  : User (enrichment; activity weight signal)
- Freshness field: activity_at_utc
- Declared PK   : activity_id (VARCHAR(100))
"""

from __future__ import annotations

from app.contracts.warehouse_rows import WarehouseRow
from app.extractors.base import BaseExtractor
from app.schemas.warehouse.user_activities import (
    FRESHNESS_FIELD,
    INCLUSION_MODE,
    PRIMARY_KEYS,
    SOURCE_NAME,
    UserActivitiesRow,
)


class UserActivitiesExtractor(BaseExtractor):
    """
    Extractor for fct_user_activities.

    Incremental strategy:
    - watermark field: activity_at_utc
    - ordering: activity_at_utc, activity_id

    Append-only event log:
    - Activity events are recorded at occurrence and are not mutated
      post-creation. activity_at_utc reliably captures all new events in
      incremental runs without rescanning historical rows.

    Nullable target, reaction, and invite fields:
    - target_id, target_type, target_owner_user_id — NULL for untargeted
      activities.
    - reaction_subtype — NULL for non-reaction activity types.
    - invite_code, invite_accepted_at — NULL for non-invite activity types.
    All preserved as NULL; transformer gates type-specific enrichment on
    non-NULL values.
    """

    source_name: str = SOURCE_NAME
    schema_row_class: type[WarehouseRow] = UserActivitiesRow
    inclusion_mode: str = INCLUSION_MODE
    freshness_field: str | None = FRESHNESS_FIELD       # activity_at_utc
    primary_key_fields: tuple[str, ...] = PRIMARY_KEYS
    default_chunk_size: int = 2000
    supports_incremental: bool = True

    # ── Source column contract ────────────────────────────────────────────────

    def get_source_columns(self) -> tuple[str, ...]:
        """
        Return the explicit ordered source columns for fct_user_activities.

        These columns must stay aligned with UserActivitiesRow.from_row().
        Adding or removing a column here requires a matching change in
        the schema row dataclass.

        activity_id note:
            VARCHAR(100) in the DWH (not int as spec suggested); extracted
            as str. Used as the ordering tiebreaker.

        activity_date_key note:
            INTEGER partition key (YYYYMMDD) in the DWH; coerced to str | None.
            Partition label only — not a quantity.

        Nullable target fields note:
            target_id, target_type, target_owner_user_id — NULL for activities
            without a specific target. target_type discriminates the entity
            class of target_id when non-NULL.

        Nullable activity-type-specific fields note:
            reaction_subtype — NULL for non-reaction activity types.
            invite_code, invite_accepted_at — NULL for non-invite activity
            types. All preserved as NULL; transformer gates on non-NULL values.
        """
        return (
            "activity_id",                  # VARCHAR(100) in DWH (not int)
            "user_id",                      # nullable string FK
            "activity_type",
            "activity_at_utc",              # extractor watermark field
            "activity_date_key",            # INTEGER partition key (YYYYMMDD) in DWH
            "target_id",                    # NULL for untargeted activities
            "target_type",                  # NULL for untargeted activities
            "target_owner_user_id",         # NULL for untargeted activities
            "reaction_subtype",             # NULL for non-reaction activity types
            "invite_code",                  # NULL for non-invite activity types
            "invite_accepted_at",           # NULL for non-invite activity types
        )

    # ── Query construction ────────────────────────────────────────────────────

    def build_base_query(self) -> str:
        """
        Return the base SELECT for fct_user_activities without incremental
        filtering.

        The incremental clause (WHERE activity_at_utc > %(watermark_value)s)
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
        Build the incremental filter using activity_at_utc.

        Uses strict greater-than semantics so watermark advancement remains
        monotonic across runs. Appropriate for an append-only event log where
        rows are created at occurrence and never mutated.

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
        Return stable deterministic ordering for fct_user_activities.

        activity_at_utc first — aligns with watermark advancement and
        clusters output chronologically by event occurrence time.

        activity_id second — VARCHAR(100) PK; breaks ties within the same
        activity_at_utc bucket deterministically. String ordering is safe
        here as activity_id is a stable identity key.
        """
        return "\nORDER BY activity_at_utc, activity_id"

    def build_pagination_clause(self, limit: int, offset: int) -> str:
        """
        Return LIMIT/OFFSET pagination clause.
        """
        return "\nLIMIT %(limit)s OFFSET %(offset)s"