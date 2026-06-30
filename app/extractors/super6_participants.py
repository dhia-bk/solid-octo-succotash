"""
Extractor for the fct_super6_participants warehouse source.

Purpose:
- Extract per-user Super6 round participation facts from
  fct_super6_participants, including user, round, total points, accuracy
  metrics, processing state, and winner flag.
- Incremental strategy using joined_at_utc as the watermark.
- Return typed Super6ParticipantsRow instances wrapped in ExtractorBatch.

Source characteristics:
    fct_super6_participants holds one row per user per Super6 round. The row
    is created when a user joins a round (joined_at_utc) and then updated
    in-place as fixture results are processed — total_points, correct_scores,
    correct_results, wrong_predictions, processed_matches, is_winner, and
    is_fully_processed all advance as the round progresses.

    Filtering by joined_at_utc captures new participants correctly on
    incremental runs but will miss score and outcome updates on existing
    participation rows. For active rounds in progress, these fields are
    expected to change frequently as each fixture result is applied.

    Pipeline operators who need accurate in-round scores and winner flags
    should schedule periodic full-refresh runs during active rounds, or
    use a bounded active-window approach keyed on the round's end_date_utc
    from dim_super6_rounds.

Design rules:
- super6_participant_id and super6_round_id are VARCHAR in the DWH;
  preserved as str / str | None. The spec suggested int — DWH type wins.
- user_id is a string FK to dim_users; preserved as-is.
- is_winner and is_fully_processed are TINYINT 0/1 lifecycle flags;
  stored as int | None per project convention. Both mutate after row creation.
- No graph logic, canonicalization, or enrichment is applied here.

Source schema:
- Source table  : fct_super6_participants
- Inclusion mode: GRAPH_CORE
- Graph entity  : PARTICIPATED_IN relationship (User → Super6Round)
- Freshness field: joined_at_utc
"""

from __future__ import annotations

from app.contracts.warehouse_rows import WarehouseRow
from app.extractors.base import BaseExtractor
from app.schemas.warehouse.super6_participants import (
    FRESHNESS_FIELD,
    INCLUSION_MODE,
    PRIMARY_KEYS,
    SOURCE_NAME,
    Super6ParticipantsRow,
)


class Super6ParticipantsExtractor(BaseExtractor):
    """
    Extractor for fct_super6_participants.

    Incremental strategy:
    - watermark field: joined_at_utc
    - ordering: joined_at_utc, super6_participant_id

    Score and outcome state limitation:
    - total_points, correct_scores, correct_results, wrong_predictions,
      processed_matches, is_winner, and is_fully_processed all update as
      fixture results are applied during an active round. Incremental runs
      by joined_at_utc capture new participants only; score updates on
      existing participants are not re-extracted. Schedule periodic
      full-refresh runs during active rounds when accurate in-round scores
      are required.
    """

    source_name: str = SOURCE_NAME
    schema_row_class: type[WarehouseRow] = Super6ParticipantsRow
    inclusion_mode: str = INCLUSION_MODE
    freshness_field: str | None = FRESHNESS_FIELD     # joined_at_utc
    primary_key_fields: tuple[str, ...] = PRIMARY_KEYS
    default_chunk_size: int = 5000
    supports_incremental: bool = True

    # ── Source column contract ────────────────────────────────────────────────

    def get_source_columns(self) -> tuple[str, ...]:
        """
        Return the explicit ordered source columns for fct_super6_participants.

        These columns must stay aligned with Super6ParticipantsRow.from_row().
        Adding or removing a column here requires a matching change in
        the schema row dataclass.

        Mutable outcome fields note:
            total_points, correct_scores, correct_results, wrong_predictions,
            processed_matches, is_winner, and is_fully_processed all update
            in-place as fixture results are applied. All must be preserved so
            the transformer has the most recently extracted outcome state,
            even if it may lag on participants in active rounds.
        """
        return (
            "super6_participant_id",
            "user_id",
            "super6_round_id",
            "joined_at_utc",
            "total_points",            # mutable — advances as results apply
            "correct_scores",          # mutable — advances as results apply
            "correct_results",         # mutable — advances as results apply
            "wrong_predictions",       # mutable — advances as results apply
            "processed_matches",       # mutable — advances as results apply
            "is_winner",               # mutable — set when round is finalised
            "is_fully_processed",      # mutable — set when all matches scored
        )

    # ── Query construction ────────────────────────────────────────────────────

    def build_base_query(self) -> str:
        """
        Return the base SELECT for fct_super6_participants without incremental
        filtering.

        The incremental clause (WHERE joined_at_utc > :watermark_value)
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
        Build the incremental filter using joined_at_utc.

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
        Return stable deterministic ordering for fct_super6_participants.

        joined_at_utc first — aligns with watermark advancement and clusters
        output by participation time.

        super6_participant_id second — VARCHAR PK; breaks ties within the
        same join timestamp bucket deterministically.
        """
        return "\nORDER BY joined_at_utc, super6_participant_id"

    def build_pagination_clause(self, limit: int, offset: int) -> str:
        """
        Return LIMIT/OFFSET pagination clause.
        """
        return "\nLIMIT %(limit)s OFFSET %(offset)s"