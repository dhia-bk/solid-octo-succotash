"""
Extractor for the dim_notification_preferences warehouse source.

Purpose:
- Extract notification consent and device registration rows from
  dim_notification_preferences, including user identity, subscription
  category, enablement state, registered device count, device platforms,
  and token update timestamps.
- Incremental strategy using preference_updated_at_utc as the watermark.
- Return typed NotificationPreferencesRow instances wrapped in ExtractorBatch.

Composite logical key — (user_id, subscription_category):
    dim_notification_preferences has one row per (user_id,
    subscription_category) pair. PRIMARY_KEYS declares only user_id (as in
    the schema), but this is not a unique row key — multiple rows per user_id
    exist, one per category. The extractor does not deduplicate; the
    transformer is responsible for grouping rows by user_id before writing
    enrichment properties to User nodes.

Watermark field — preference_updated_at_utc:
    preference_updated_at_utc is the correct incremental field because rows
    mutate when users change their consent state (is_enabled flips),
    register new devices (registered_device_count, device_platforms change),
    or refresh push tokens (last_token_updated_at advances).
    preference_updated_at_utc advances on each mutation, ensuring incremental
    runs capture all consent and device state changes, not just newly created
    preference rows.

Design rules:
- user_id is a string (not an integer); ordering uses string collation.
- subscription_category is included in ORDER BY as the tiebreaker within
  the same (preference_updated_at_utc, user_id) bucket, producing a fully
  deterministic row sequence given the (user_id, subscription_category)
  composite logical key.
- is_enabled is TINYINT 0/1 in the DWH; extracted as int | None, not bool.
- device_platforms is a raw TEXT field (comma-separated or JSON string);
  extracted as-is without parsing — parsing belongs to the transformer.
- No graph logic, grouping, or enrichment merging is applied here.

Source schema:
- Source table  : dim_notification_preferences
- Inclusion mode: GRAPH_ENRICHMENT
- Graph entity  : User (enrichment)
- Freshness field: preference_updated_at_utc
- Declared PK   : user_id (logical key is (user_id, subscription_category))
"""

from __future__ import annotations

from app.contracts.warehouse_rows import WarehouseRow
from app.extractors.base import BaseExtractor
from app.schemas.warehouse.notification_preferences import (
    FRESHNESS_FIELD,
    INCLUSION_MODE,
    PRIMARY_KEYS,
    SOURCE_NAME,
    NotificationPreferencesRow,
)


class NotificationPreferencesExtractor(BaseExtractor):
    """
    Extractor for dim_notification_preferences.

    Incremental strategy:
    - watermark field: preference_updated_at_utc
    - ordering: preference_updated_at_utc, user_id, subscription_category

    Composite logical key:
    - One row per (user_id, subscription_category). PRIMARY_KEYS declares
      user_id per schema convention, but is not a unique row key. The
      extractor emits all rows as received; the transformer groups by user_id
      before writing enrichment properties to User nodes.

    Mutation coverage:
    - preference_updated_at_utc advances on consent state changes, device
      registration updates, and token refreshes, ensuring all preference
      mutations are captured incrementally.

    device_platforms:
    - Raw TEXT field (comma-separated or JSON string). Extracted as-is;
      parsing belongs to the transformer layer.
    """

    source_name: str = SOURCE_NAME
    schema_row_class: type[WarehouseRow] = NotificationPreferencesRow
    inclusion_mode: str = INCLUSION_MODE
    freshness_field: str | None = FRESHNESS_FIELD       # preference_updated_at_utc
    primary_key_fields: tuple[str, ...] = PRIMARY_KEYS
    default_chunk_size: int = 1000
    supports_incremental: bool = True

    # ── Source column contract ────────────────────────────────────────────────

    def get_source_columns(self) -> tuple[str, ...]:
        """
        Return the explicit ordered source columns for dim_notification_preferences.

        These columns must stay aligned with NotificationPreferencesRow.from_row().
        Adding or removing a column here requires a matching change in
        the schema row dataclass.

        is_enabled note:
            TINYINT 0/1 in the DWH; coerced to int | None. Not a Python bool.

        device_platforms note:
            Raw TEXT field (comma-separated or JSON string). Extracted as-is
            without parsing — parsing belongs to the transformer layer.

        Composite key note:
            One row per (user_id, subscription_category). user_id alone is
            not a unique row key. The transformer must group by user_id before
            writing User node enrichment properties.
        """
        return (
            "user_id",
            "subscription_category",            # part of composite logical key
            "is_enabled",                       # TINYINT 0/1 in DWH (not bool)
            "preference_created_at_utc",
            "preference_updated_at_utc",        # extractor watermark field
            "registered_device_count",
            "last_token_updated_at",
            "device_platforms",                 # raw TEXT — do not parse here
        )

    # ── Query construction ────────────────────────────────────────────────────

    def build_base_query(self) -> str:
        """
        Return the base SELECT for dim_notification_preferences without
        incremental filtering.

        The incremental clause
        (WHERE preference_updated_at_utc > :watermark_value) is appended
        by the base runtime via build_incremental_clause().
        """
        columns = ",\n    ".join(self.get_source_columns())
        return f"""
SELECT
    {columns}
FROM {self.source_name}
""".strip()

    def build_incremental_clause(self, watermark_value: str | None) -> str:
        """
        Build the incremental filter using preference_updated_at_utc.

        Uses strict greater-than semantics so watermark advancement remains
        monotonic across runs. Covers consent state changes, device
        registration updates, and token refreshes in addition to newly
        created preference rows.

        No clause is emitted on first run (watermark is None), triggering a
        full-table bootstrap load.
        """
        if not self.supports_incremental or not self.freshness_field:
            return ""

        if not watermark_value:
            return ""

        return f"\nWHERE {self.freshness_field} > :watermark_value"

    def build_order_by_clause(self) -> str:
        """
        Return stable deterministic ordering for dim_notification_preferences.

        preference_updated_at_utc first — aligns with watermark advancement
        and clusters output by most recent preference mutation.

        user_id second — string PK per schema declaration; groups all
        category rows for the same user together within each watermark bucket,
        which benefits transformer grouping by user_id.

        subscription_category third — resolves ties within the same
        (preference_updated_at_utc, user_id) bucket, producing a fully
        deterministic sequence given the (user_id, subscription_category)
        composite logical key.
        """
        return "\nORDER BY preference_updated_at_utc, user_id, subscription_category"

    def build_pagination_clause(self, limit: int, offset: int) -> str:
        """
        Return LIMIT/OFFSET pagination clause.
        """
        return "\nLIMIT %(limit)s OFFSET %(offset)s"