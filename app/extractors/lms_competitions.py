"""
Extractor for the dim_lms_competitions warehouse source.

Purpose:
- Extract Last Man Standing competition rows from dim_lms_competitions,
  including identity, creator, season, participant counts, elimination rules,
  status, and winner fields.
- Incremental strategy using created_at as the watermark.
- Return typed LmsCompetitionsRow instances wrapped in ExtractorBatch.

Source characteristics:
    dim_lms_competitions holds one row per LMS competition. Competitions are
    created within a private league context and progress through a lifecycle
    (status, current_round, survivors_remaining, winner_user_id,
    completed_at, winning_date) as rounds are played and participants are
    eliminated.

    Filtering by created_at captures new competitions correctly on incremental
    runs but will miss lifecycle state updates on existing competitions.
    current_participants, survivors_remaining, current_round, status,
    winner_user_id, completed_at, and winning_date all mutate after creation.

    Pipeline operators who need accurate live state on ongoing competitions
    should schedule periodic full-refresh runs or bound the extraction window
    to active competitions (status != 'completed').

No declared PK constraint:
    The DWH has no declared unique constraint on lms_competition_id. It is
    treated as the stable de facto key at extraction time. The extractor must
    preserve it exactly and must not attempt to deduplicate rows — that is
    a transformer concern if duplicates are detected.

Design rules:
- lms_competition_id is VARCHAR(50); preserved as str.
- private_league_id is an integer FK to dim_private_leagues; preserved as-is.
- created_by_user_id and winner_user_id are string FKs to dim_users;
  both must be preserved for node and edge construction.
- Mutable lifecycle fields (status, current_round, survivors_remaining,
  winner_user_id, completed_at, winning_date, current_participants) are
  extracted faithfully at whatever state they hold at extraction time.
- No graph logic, canonicalization, or enrichment is applied here.

Source schema:
- Source table  : dim_lms_competitions
- Inclusion mode: GRAPH_CORE
- Graph entity  : LMSCompetition
- Freshness field: created_at
- Declared PK   : None (lms_competition_id treated as stable de facto key)
"""

from __future__ import annotations

from app.contracts.warehouse_rows import WarehouseRow
from app.extractors.base import BaseExtractor
from app.schemas.warehouse.lms_competitions import (
    FRESHNESS_FIELD,
    INCLUSION_MODE,
    PRIMARY_KEYS,
    SOURCE_NAME,
    LmsCompetitionsRow,
)


class LmsCompetitionsExtractor(BaseExtractor):
    """
    Extractor for dim_lms_competitions.

    Incremental strategy:
    - watermark field: created_at
    - ordering: created_at, lms_competition_id

    Lifecycle state limitation:
    - current_participants, survivors_remaining, current_round, status,
      winner_user_id, completed_at, and winning_date all mutate after
      competition creation. Incremental runs capture new competitions only;
      lifecycle updates on existing competitions are not re-extracted.
      Schedule periodic full-refresh runs when accurate live state is required.

    No declared PK:
    - lms_competition_id is treated as the stable de facto key. The extractor
      preserves all rows as received; deduplication is a transformer concern.
    """

    source_name: str = SOURCE_NAME
    schema_row_class: type[WarehouseRow] = LmsCompetitionsRow
    inclusion_mode: str = INCLUSION_MODE
    freshness_field: str | None = FRESHNESS_FIELD     # created_at
    primary_key_fields: tuple[str, ...] = PRIMARY_KEYS
    default_chunk_size: int = 2000                   
    supports_incremental: bool = True

    # ── Source column contract ────────────────────────────────────────────────

    def get_source_columns(self) -> tuple[str, ...]:
        """
        Return the explicit ordered source columns for dim_lms_competitions.

        These columns must stay aligned with LmsCompetitionsRow.from_row().
        Adding or removing a column here requires a matching change in
        the schema row dataclass.

        Mutable lifecycle fields note:
            current_participants, survivors_remaining, current_round, status,
            winner_user_id, completed_at, and winning_date can all change
            after competition creation. All are extracted at their current
            state; see class docstring for the incremental limitation.

        No-PK note:
            lms_competition_id has no declared unique constraint in the DWH.
            Extracted as-is; deduplication belongs to the transformer layer.
        """
        return (
            "lms_competition_id",
            "private_league_id",
            "competition_name",
            "created_by_user_id",
            "season_year",
            "start_gameweek",
            "end_gameweek",
            "entry_fee_coins",
            "prize_pool_coins",
            "max_participants",
            "current_participants",   # mutable — advances as entries arrive
            "survivors_remaining",    # mutable — decrements each round
            "elimination_rule",
            "status",                 # mutable — lifecycle progression
            "winner_user_id",         # mutable — NULL until competition ends
            "completed_at",           # mutable — NULL until competition ends
            "created_at",
            "current_round",          # mutable — increments each gameweek
            "winning_date",           # mutable — NULL until competition ends
        )

    # ── Query construction ────────────────────────────────────────────────────

    def build_base_query(self) -> str:
        """
        Return the base SELECT for dim_lms_competitions without incremental
        filtering.

        The incremental clause (WHERE created_at > :watermark_value)
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
        Build the incremental filter using created_at.

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
        Return stable deterministic ordering for dim_lms_competitions.

        created_at first — aligns with watermark advancement and clusters
        output by competition creation time.

        lms_competition_id second — VARCHAR de facto PK; breaks ties within
        the same created_at timestamp bucket deterministically.
        """
        return "\nORDER BY created_at, lms_competition_id"

    def build_pagination_clause(self, limit: int, offset: int) -> str:
        """
        Return LIMIT/OFFSET pagination clause.
        """
        return "\nLIMIT %(limit)s OFFSET %(offset)s"