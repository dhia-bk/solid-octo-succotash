"""
Extractor for the fct_team_affinity warehouse source.

Purpose:
- Extract user-to-team affinity score rows from fct_team_affinity, including
  user and team identity, fan classification flags (favorite, active, local),
  affinity type, prediction analytics (total, correct, accuracy rate, points,
  bias), mention counts, date-range bounds, engagement frequency, and the
  affinity calculation timestamp.
- Incremental strategy using calculated_at_utc as the watermark.
- Return typed TeamAffinityRow instances wrapped in ExtractorBatch.

Graph entity — HAS_AFFINITY relationship:
    fct_team_affinity is GRAPH_CORE but feeds a relationship entity rather
    than a node. Each row represents a HAS_AFFINITY edge between a User node
    and a Team node, enriched with affinity score properties. The extractor
    is not responsible for edge creation or property mapping — that belongs
    to the transformer layer.

Watermark field — calculated_at_utc:
    calculated_at_utc is the correct incremental field because affinity scores
    are recomputed periodically as users accumulate new predictions, posts,
    and engagement activity. Each recomputation advances calculated_at_utc,
    ensuring incremental runs capture the latest affinity state for all
    user-team pairs recalculated since the previous run.

Nullable user and team fields:
    user_id and team_id are nullable string FKs (VARCHAR(100) in the DWH).
    Both are extracted faithfully as NULL; the transformer must gate
    HAS_AFFINITY edge creation on non-NULL user_id and team_id, as an edge
    with either endpoint missing cannot be written to the graph.

Date-only prediction date fields:
    first_prediction_date and last_prediction_date are DATE columns in the
    DWH (date-only semantics). They are extracted as str | None without
    datetime coercion to avoid spurious timezone shifts on date-only values.
    No warehouse_value_to_utc_datetime call is applied to these fields.

Design rules:
- affinity_id is VARCHAR(100) in the DWH (not int as spec suggested);
  extracted as str. Used as the ordering tiebreaker.
- team_id is VARCHAR(100) in the DWH (not int); extracted as str | None.
- is_favorite_team, is_active_fan, is_local_fan are TINYINT 0/1; extracted
  as int | None, not bool.
- prediction_accuracy_rate and total_points_earned are DECIMAL in the DWH;
  coerced to float | None.
- No graph logic, edge creation, or property canonicalization here.

Source schema:
- Source table  : fct_team_affinity
- Inclusion mode: GRAPH_CORE
- Graph entity  : HAS_AFFINITY (User → Team relationship)
- Freshness field: calculated_at_utc
- Declared PK   : affinity_id (VARCHAR(100))
"""

from __future__ import annotations

from app.contracts.warehouse_rows import WarehouseRow
from app.extractors.base import BaseExtractor
from app.schemas.warehouse.team_affinity import (
    FRESHNESS_FIELD,
    INCLUSION_MODE,
    PRIMARY_KEYS,
    SOURCE_NAME,
    TeamAffinityRow,
)


class TeamAffinityExtractor(BaseExtractor):
    """
    Extractor for fct_team_affinity.

    Incremental strategy:
    - watermark field: calculated_at_utc
    - ordering: calculated_at_utc, affinity_id

    Recomputation coverage:
    - Affinity scores are periodically recomputed as user behaviour evolves.
      calculated_at_utc advances on each recomputation, ensuring incremental
      runs capture the latest affinity state for all recalculated user-team
      pairs, not only newly created affinity rows.

    Nullable user and team fields:
    - user_id and team_id are NULL when the FK reference is absent. The
      transformer must gate HAS_AFFINITY edge creation on non-NULL values for
      both endpoints; an edge with a missing User or Team cannot be written
      to the graph.

    Date-only prediction date fields:
    - first_prediction_date and last_prediction_date are DATE columns;
      extracted as str | None without datetime coercion. See module docstring.
    """

    source_name: str = SOURCE_NAME
    schema_row_class: type[WarehouseRow] = TeamAffinityRow
    inclusion_mode: str = INCLUSION_MODE
    freshness_field: str | None = FRESHNESS_FIELD       # calculated_at_utc
    primary_key_fields: tuple[str, ...] = PRIMARY_KEYS
    default_chunk_size: int = 2000
    supports_incremental: bool = True

    # ── Source column contract ────────────────────────────────────────────────

    def get_source_columns(self) -> tuple[str, ...]:
        """
        Return the explicit ordered source columns for fct_team_affinity.

        These columns must stay aligned with TeamAffinityRow.from_row().
        Adding or removing a column here requires a matching change in
        the schema row dataclass.

        affinity_id / team_id note:
            VARCHAR(100) in the DWH (not int as spec suggested); extracted
            as str / str | None respectively.

        is_favorite_team / is_active_fan / is_local_fan note:
            TINYINT 0/1 in the DWH; coerced to int | None. Not Python bools.

        prediction_accuracy_rate / total_points_earned note:
            DECIMAL in the DWH; coerced to float | None.

        first_prediction_date / last_prediction_date note:
            DATE columns in the DWH (date-only; no time component). Extracted
            as str | None without datetime coercion to avoid spurious timezone
            shifts on date-only values.

        user_id / team_id nullable note:
            NULL when the FK reference is absent. Transformer must gate
            HAS_AFFINITY edge creation on non-NULL values for both endpoints.
        """
        return (
            "affinity_id",                      # VARCHAR(100) in DWH (not int)
            "user_id",                          # nullable VARCHAR FK
            "team_id",                          # nullable VARCHAR(100) in DWH (not int)
            "team_name",
            "is_favorite_team",                 # TINYINT 0/1 in DWH (not bool)
            "affinity_type",
            "total_predictions",
            "correct_predictions",
            "prediction_accuracy_rate",         # DECIMAL(5,2) in DWH
            "total_points_earned",              # DECIMAL(10,2) in DWH
            "posts_mentioning_team",
            "comments_mentioning_team",
            "first_prediction_date",            # DATE column; str in row; no tz coercion
            "last_prediction_date",             # DATE column; str in row; no tz coercion
            "days_since_last_prediction",
            "is_active_fan",                    # TINYINT 0/1 in DWH (not bool)
            "engagement_frequency",
            "prediction_bias",
            "user_country",
            "team_country",
            "is_local_fan",                     # TINYINT 0/1 in DWH (not bool)
            "calculated_at_utc",                # extractor watermark field
        )

    # ── Query construction ────────────────────────────────────────────────────

    def build_base_query(self) -> str:
        """
        Return the base SELECT for fct_team_affinity without incremental
        filtering.

        The incremental clause (WHERE calculated_at_utc > :watermark_value)
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
        Build the incremental filter using calculated_at_utc.

        Uses strict greater-than semantics so watermark advancement remains
        monotonic across runs. Covers affinity score recomputations in
        addition to newly created affinity rows — any user-team pair
        recalculated since the last run will have an advanced
        calculated_at_utc and will be captured.

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
        Return stable deterministic ordering for fct_team_affinity.

        calculated_at_utc first — aligns with watermark advancement and
        clusters output by most recent affinity recomputation batch.

        affinity_id second — VARCHAR(100) de facto PK; breaks ties within
        the same calculated_at_utc bucket deterministically. String ordering
        is safe here as affinity_id is a stable identity key.
        """
        return "\nORDER BY calculated_at_utc, affinity_id"

    def build_pagination_clause(self, limit: int, offset: int) -> str:
        """
        Return LIMIT/OFFSET pagination clause.
        """
        return "\nLIMIT %(limit)s OFFSET %(offset)s"