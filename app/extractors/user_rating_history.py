"""
Extractor for the fct_user_rating_history warehouse source.

Purpose:
- Extract ELO-style duel rating change event rows from fct_user_rating_history,
  including user and duel identity, previous rating, new rating, change delta,
  change reason, event timestamp, and partition date key.
- Incremental strategy using created_at_utc as the watermark.
- Return typed UserRatingHistoryRow instances wrapped in ExtractorBatch.

Watermark field — created_at_utc:
    created_at_utc is the correct incremental field because
    fct_user_rating_history is an append-only rating event log — each row
    represents a discrete ELO rating change at a point in time and is not
    mutated post-creation. New rating events always carry a created_at_utc
    beyond the previous watermark, ensuring incremental runs capture all
    newly recorded rating changes without rescanning historical rows.

No declared PK:
    fct_user_rating_history has no declared PK constraint in the DWH.
    rating_event_id is VARCHAR(100) and is treated as the stable unique
    identifier. The extractor does not deduplicate rows — that is a
    transformer concern if duplicates are detected.

Nullable user and duel fields:
    user_id is NULL when the FK reference is absent; the transformer must
    gate HAS_RATING edge creation on non-NULL user_id, as a rating snapshot
    with no owning User cannot be written to the graph.
    duel_id is NULL for rating events not originating from a specific duel
    (e.g. manual adjustments or seeding events). Extracted faithfully; the
    transformer gates duel-edge creation on non-NULL values.

Integer-to-float semantic override:
    previous_rating, new_rating, and change_amount are INTEGER in the DWH
    but are exposed as float | None in the row dataclass. This is an
    intentional semantic override: ELO ratings are conceptually continuous
    and the model is expected to gain decimal precision as it evolves.
    The float type also aligns with duel_rating on the User node, preventing
    type mismatches at graph write time. The extractor faithfully coerces
    these fields to float as declared by the schema.

Design rules:
- rating_event_id is VARCHAR(100) with no declared PK constraint; treated
  as the stable unique identifier and used as the ordering tiebreaker.
- rating_date_key is an INTEGER partition key (YYYYMMDD) in the DWH; coerced
  to str | None — partition label, not a quantity.
- No graph logic, rating computation, or edge creation here.

Source schema:
- Source table  : fct_user_rating_history
- Inclusion mode: GRAPH_CORE
- Graph entity  : RatingSnapshot
- Freshness field: created_at_utc
- Declared PK   : none (rating_event_id treated as stable unique identifier)
"""

from __future__ import annotations

from app.contracts.warehouse_rows import WarehouseRow
from app.extractors.base import BaseExtractor
from app.schemas.warehouse.user_rating_history import (
    FRESHNESS_FIELD,
    INCLUSION_MODE,
    PRIMARY_KEYS,
    SOURCE_NAME,
    UserRatingHistoryRow,
)


class UserRatingHistoryExtractor(BaseExtractor):
    """
    Extractor for fct_user_rating_history.

    Incremental strategy:
    - watermark field: created_at_utc
    - ordering: created_at_utc, rating_event_id

    Append-only event log:
    - Rating change events are recorded at occurrence and are not mutated
      post-creation. created_at_utc reliably captures all new rating events
      in incremental runs without rescanning historical rows.

    Nullable user and duel fields:
    - user_id is NULL when the FK reference is absent. Transformer must gate
      HAS_RATING edge creation on non-NULL user_id — a RatingSnapshot with
      no owning User cannot be written to the graph.
    - duel_id is NULL for non-duel-originating rating events (e.g. manual
      adjustments, seeding). Extracted faithfully; transformer gates
      duel-edge creation on non-NULL values.

    Integer-to-float coercion:
    - previous_rating, new_rating, and change_amount are INTEGER in the DWH
      but coerced to float | None per schema declaration. See module docstring
      for rationale.
    """

    source_name: str = SOURCE_NAME
    schema_row_class: type[WarehouseRow] = UserRatingHistoryRow
    inclusion_mode: str = INCLUSION_MODE
    freshness_field: str | None = FRESHNESS_FIELD       # created_at_utc
    primary_key_fields: tuple[str, ...] = PRIMARY_KEYS
    default_chunk_size: int = 2000
    supports_incremental: bool = True

    # ── Source column contract ────────────────────────────────────────────────

    def get_source_columns(self) -> tuple[str, ...]:
        """
        Return the explicit ordered source columns for fct_user_rating_history.

        These columns must stay aligned with UserRatingHistoryRow.from_row().
        Adding or removing a column here requires a matching change in
        the schema row dataclass.

        previous_rating / new_rating / change_amount note:
            INTEGER in the DWH; coerced to float | None in the row dataclass.
            Semantic override for ELO rating continuity — see module docstring.

        rating_date_key note:
            INTEGER partition key (YYYYMMDD) in the DWH; coerced to str | None.
            Partition label only — not a quantity.

        No-PK note:
            rating_event_id is VARCHAR(100) with no declared PK constraint.
            Treated as the stable unique identifier; deduplication belongs to
            the transformer layer.

        user_id / duel_id nullable note:
            user_id — NULL when FK reference is absent; transformer gates
                HAS_RATING edge creation on non-NULL values.
            duel_id — NULL for non-duel-originating rating events; transformer
                gates duel-edge creation on non-NULL values.
        """
        return (
            "rating_event_id",          # VARCHAR(100); stable unique id; no PK constraint
            "user_id",                  # nullable string FK
            "duel_id",                  # nullable string FK; NULL for non-duel events
            "previous_rating",          # INTEGER in DWH; coerced to float | None
            "new_rating",               # INTEGER in DWH; coerced to float | None
            "change_amount",            # INTEGER in DWH; coerced to float | None
            "reason",
            "created_at_utc",           # extractor watermark field
            "rating_date_key",          # INTEGER partition key (YYYYMMDD) in DWH
        )

    # ── Query construction ────────────────────────────────────────────────────

    def build_base_query(self) -> str:
        """
        Return the base SELECT for fct_user_rating_history without incremental
        filtering.

        The incremental clause (WHERE created_at_utc > :watermark_value)
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
        Build the incremental filter using created_at_utc.

        Uses strict greater-than semantics so watermark advancement remains
        monotonic across runs. Appropriate for an append-only event log where
        rating events are created at occurrence and never mutated.

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
        Return stable deterministic ordering for fct_user_rating_history.

        created_at_utc first — aligns with watermark advancement and clusters
        output chronologically by rating event occurrence time, which produces
        a naturally ascending rating progression sequence per user.

        rating_event_id second — VARCHAR(100) stable unique identifier; breaks
        ties within the same created_at_utc bucket deterministically. String
        ordering is safe here as rating_event_id is a stable identity key.
        """
        return "\nORDER BY created_at_utc, rating_event_id"

    def build_pagination_clause(self, limit: int, offset: int) -> str:
        """
        Return LIMIT/OFFSET pagination clause.
        """
        return "\nLIMIT %(limit)s OFFSET %(offset)s"