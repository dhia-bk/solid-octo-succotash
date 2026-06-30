"""
Extractor for the fct_awards_and_achievements warehouse source.

Purpose:
- Extract achievement and award events from fct_awards_and_achievements,
  including user, badge/trophy fields, reward amount, private league context,
  and earned timestamp.
- Incremental strategy using earned_at_utc as the watermark.
- Return typed AwardsAndAchievementsRow instances wrapped in ExtractorBatch.

VARCHAR timestamp — earned_at_utc:
    earned_at_utc is stored as VARCHAR(255) in the DWH (ISO string, not a
    native DATETIME column), matching the same pattern as
    fct_chatbot_messages.message_at_utc. The watermark comparison in the
    incremental clause performs a string comparison against the DWH column.
    This is safe as long as the ISO format is consistently zero-padded
    (YYYY-MM-DDTHH:MM:SS or YYYY-MM-DD HH:MM:SS) — string and datetime
    ordering are equivalent under these conditions.
    warehouse_value_to_utc_datetime in from_row() handles the Python-level
    normalization to a proper datetime object.

Source characteristics:
    fct_awards_and_achievements is an append-oriented event log — one row per
    achievement or award event. Rows are written once and not updated after
    initial insert. Incremental extraction by earned_at_utc is therefore
    complete and correct with no mutation window required.

    Each row can represent either a badge achievement (badge_id, badge_name
    populated) or a trophy achievement (trophy_id, trophy_name,
    trophy_description populated). The two achievement types are distinguished
    by achievement_type; the transformer routes graph node creation
    accordingly. All badge and trophy fields must be preserved regardless of
    which type is present on a given row.

    private_league_id links achievements that were earned within the context
    of a specific private league (e.g. league-specific trophies). It is NULL
    for platform-wide achievements. Both states are semantically significant.

Design rules:
- award_id is VARCHAR(255); preserved as str.
- earned_at_utc is a VARCHAR ISO string in the DWH; the incremental WHERE
  clause compares strings directly. See VARCHAR timestamp note above.
- reward_amount is DOUBLE in the DWH; stored as float | None.
- badge_id, trophy_id, and private_league_id are integer FKs; preserved
  as int | None.
- No graph logic, canonicalization, or enrichment is applied here.

Source schema:
- Source table  : fct_awards_and_achievements
- Inclusion mode: GRAPH_CORE
- Graph entity  : Achievement node + ACHIEVED relationship (User → Achievement)
- Freshness field: earned_at_utc (VARCHAR ISO string in DWH)
"""

from __future__ import annotations

from app.contracts.warehouse_rows import WarehouseRow
from app.extractors.base import BaseExtractor
from app.schemas.warehouse.awards_and_achievements import (
    FRESHNESS_FIELD,
    INCLUSION_MODE,
    PRIMARY_KEYS,
    SOURCE_NAME,
    AwardsAndAchievementsRow,
)


class AwardsAndAchievementsExtractor(BaseExtractor):
    """
    Extractor for fct_awards_and_achievements.

    Incremental strategy:
    - watermark field: earned_at_utc
    - ordering: earned_at_utc, award_id

    VARCHAR timestamp note:
    - earned_at_utc is stored as an ISO string in the DWH, not a native
      DATETIME. The incremental WHERE clause compares strings directly.
      Valid as long as the ISO format is consistently zero-padded.

    Dual achievement type:
    - Each row is either a badge or a trophy event, distinguished by
      achievement_type. Both badge and trophy field sets are always selected;
      the transformer routes graph node creation based on achievement_type.

    Append-oriented semantics:
    - Achievement events are written once and not updated. Incremental
      extraction is therefore complete and correct.
    """

    source_name: str = SOURCE_NAME
    schema_row_class: type[WarehouseRow] = AwardsAndAchievementsRow
    inclusion_mode: str = INCLUSION_MODE
    freshness_field: str | None = FRESHNESS_FIELD     # earned_at_utc
    primary_key_fields: tuple[str, ...] = PRIMARY_KEYS
    default_chunk_size: int = 5000
    supports_incremental: bool = True

    # ── Source column contract ────────────────────────────────────────────────

    def get_source_columns(self) -> tuple[str, ...]:
        """
        Return the explicit ordered source columns for fct_awards_and_achievements.

        These columns must stay aligned with AwardsAndAchievementsRow.from_row().
        Adding or removing a column here requires a matching change in
        the schema row dataclass.

        VARCHAR timestamp note:
            earned_at_utc is stored as an ISO string in the DWH; from_row()
            normalises to datetime via warehouse_value_to_utc_datetime. No
            SQL CAST applied.

        Dual achievement type note:
            badge_id, badge_name — populated for badge achievement events.
            trophy_id, trophy_name, trophy_description — populated for trophy
            achievement events. The non-relevant set will be NULL. Both sets
            must be selected; achievement_type discriminates at the transformer.

        private_league_id note:
            NULL for platform-wide achievements; non-NULL for league-specific
            achievements. Both states are semantically significant.

        reward_amount note:
            DOUBLE in the DWH; stored as float | None. Downstream coin/reward
            aggregations should use precision-safe arithmetic.
        """
        return (
            "award_id",
            "achievement_type",         # discriminator: badge vs trophy
            "badge_id",                 # badge achievement FK — NULL for trophy events
            "badge_name",               # badge achievement label — NULL for trophy events
            "earned_at_utc",            # VARCHAR ISO string in DWH — see timestamp note
            "earned_date_key",          # INTEGER partition label; str | None
            "private_league_id",        # NULL for platform-wide; non-NULL for league
            "reward_amount",            # DOUBLE — float | None
            "trophy_description",       # trophy achievement — NULL for badge events
            "trophy_id",                # trophy achievement FK — NULL for badge events
            "trophy_name",              # trophy achievement label — NULL for badge events
            "user_id",
            "created_at",
        )

    # ── Query construction ────────────────────────────────────────────────────

    def build_base_query(self) -> str:
        """
        Return the base SELECT for fct_awards_and_achievements without
        incremental filtering.

        The incremental clause (WHERE earned_at_utc > :watermark_value)
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
        Build the incremental filter using earned_at_utc.

        Uses strict greater-than semantics so watermark advancement remains
        monotonic across runs. String comparison against the VARCHAR ISO
        timestamp column is valid as long as the stored format is consistently
        zero-padded. No clause is emitted on first run, triggering a
        full-table bootstrap load.
        """
        if not self.supports_incremental or not self.freshness_field:
            return ""

        if not watermark_value:
            return ""

        return f"\nWHERE {self.freshness_field} > :watermark_value"

    def build_order_by_clause(self) -> str:
        """
        Return stable deterministic ordering for fct_awards_and_achievements.

        earned_at_utc first — aligns with watermark advancement and clusters
        output by achievement time.

        award_id second — VARCHAR PK; breaks ties within the same earned
        timestamp bucket deterministically.
        """
        return "\nORDER BY earned_at_utc, award_id"

    def build_pagination_clause(self, limit: int, offset: int) -> str:
        """
        Return LIMIT/OFFSET pagination clause.
        """
        return "\nLIMIT %(limit)s OFFSET %(offset)s"