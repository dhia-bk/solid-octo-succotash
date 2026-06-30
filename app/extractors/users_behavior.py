"""
Extractor for the fct_user_behavior warehouse source.

Purpose:
- Extract persona and behaviour model inputs from fct_user_behavior,
  including behaviour_label, birfing_coefficient, frustration_bias,
  pcm_stage, and last_calculated_at.
- Incremental strategy using last_calculated_at as the watermark.
- Return typed UserBehaviorRow instances wrapped in ExtractorBatch.

Source characteristics:
    fct_user_behavior holds one row per user, recomputed by the behaviour
    model on a scheduled cadence. The table is not an event log — it is a
    current-state snapshot per user. Rows are upserted (not appended) by
    the model pipeline, so last_calculated_at advances each time the model
    recalculates a user's signals.

    Incremental extraction by last_calculated_at therefore captures only
    users whose behaviour profile was refreshed since the last pipeline run,
    which is the correct and efficient extraction strategy for this source.

    On first run (no watermark), all users are extracted as a bootstrap load.

Design rules:
- id is an INTEGER surrogate PK in the DWH. UserBehaviorRow stores it as
  int; it is the stable ordering tiebreaker within a timestamp bucket.
- user_id is the join key to dim_users (string-typed). Preserved as-is;
  no coercion is applied in SQL.
- birfing_coefficient and frustration_bias are FLOAT in the DWH; stored as
  float | None in the typed row.
- These rows are enrichment inputs to PersonaState node construction, not
  the PersonaState node itself. No graph logic is applied here.
- No canonicalization or graph mapping is applied here.

Source schema:
- Source table  : fct_user_behavior
- Inclusion mode: GRAPH_ENRICHMENT
- Graph entity  : PersonaState (enrichment input)
- Freshness field: last_calculated_at
"""

from __future__ import annotations

from app.contracts.warehouse_rows import WarehouseRow
from app.extractors.base import BaseExtractor
from app.schemas.warehouse.user_behavior import (
    FRESHNESS_FIELD,
    INCLUSION_MODE,
    PRIMARY_KEYS,
    SOURCE_NAME,
    UserBehaviorRow,
)


class UserBehaviorExtractor(BaseExtractor):
    """
    Extractor for fct_user_behavior.

    Incremental strategy:
    - watermark field: last_calculated_at
    - ordering: last_calculated_at, id

    One-row-per-user semantics:
    - The table is a current-state snapshot, not an event log.
    - Each incremental run captures only users whose behaviour model
      was recalculated since the last watermark.
    - The full-table bootstrap (no watermark) loads all user profiles.
    """

    source_name: str = SOURCE_NAME
    schema_row_class: type[WarehouseRow] = UserBehaviorRow
    inclusion_mode: str = INCLUSION_MODE
    freshness_field: str | None = FRESHNESS_FIELD     # last_calculated_at
    primary_key_fields: tuple[str, ...] = PRIMARY_KEYS
    default_chunk_size: int = 5000                    
    supports_incremental: bool = True

    # ── Source column contract ────────────────────────────────────────────────

    def get_source_columns(self) -> tuple[str, ...]:
        """
        Return the explicit ordered source columns for fct_user_behavior.

        These columns must stay aligned with UserBehaviorRow.from_row().
        Adding or removing a column here requires a matching change in
        the schema row dataclass.
        """
        return (
            "id",
            "user_id",
            "behaviour_label",
            "birfing_coefficient",
            "frustration_bias",
            "total_sessions",
            "total_engagement_signals",
            "pcm_stage",
            "last_calculated_at",
        )

    # ── Query construction ────────────────────────────────────────────────────

    def build_base_query(self) -> str:
        """
        Return the base SELECT wrapped in a LAG-based state-change filter.

        The inner subquery computes the previous (behaviour_label, pcm_stage)
        per user using a window function over the full table, so cross-batch
        deduplication is correct regardless of chunk size.

        Only rows where at least one of those two fields changed from the
        previous snapshot for the same user are returned — the first row per
        user (LAG = NULL) is always included.
        """
        columns = ",\n    ".join(self.get_source_columns())
        return f"""
SELECT
    {columns}
FROM (
    SELECT *,
        LAG(behaviour_label) OVER (PARTITION BY user_id ORDER BY last_calculated_at, id) AS _prev_label,
        LAG(pcm_stage)       OVER (PARTITION BY user_id ORDER BY last_calculated_at, id) AS _prev_stage
    FROM {self.source_name}
) _state_changes
WHERE (_prev_label IS NULL OR _prev_label != behaviour_label OR _prev_stage != pcm_stage)""".strip()

    def build_incremental_clause(self, watermark_value: str | None) -> str:
        """
        Build the incremental filter using last_calculated_at.

        The watermark filter must be AND-appended (not WHERE) because the
        base query already has a WHERE clause for state-change deduplication.

        For incremental runs the LAG window is computed over the full table so
        the first new row per user correctly compares against its actual
        previous state, even if that previous row is before the watermark.
        """
        if not self.supports_incremental or not self.freshness_field:
            return ""

        if not watermark_value:
            return ""

        return f"\n  AND {self.freshness_field} > :watermark_value"

    def build_order_by_clause(self) -> str:
        """
        Return stable deterministic ordering for fct_user_behavior.

        last_calculated_at first — aligns with watermark advancement and
        groups recently recalculated profiles together.

        id second — integer surrogate PK; breaks ties within the same
        calculation timestamp bucket deterministically.
        """
        return "\nORDER BY last_calculated_at, id"

    def build_pagination_clause(self, limit: int, offset: int) -> str:
        """
        Return LIMIT/OFFSET pagination clause.
        """
        return "\nLIMIT %(limit)s OFFSET %(offset)s"