"""
Extractor for the dim_badges warehouse source.

Purpose:
- Extract badge catalog rows from dim_badges, including badge identity,
  image, description, award count, and adoption rate.
- Full-refresh strategy on every run — no timestamp column exists in the DWH.
- Return typed BadgesRow instances wrapped in ExtractorBatch.

Full-refresh strategy:
    dim_badges is a static dimension with no freshness field. The badge
    catalog changes infrequently (new badge types are rare releases) and
    contains no timestamp column by which incremental filtering could be
    applied. A full table scan on every run is correct and cheap given the
    expected low cardinality of the badge catalog.

    supports_incremental is False and freshness_field is None. The base
    runtime will emit no WHERE clause and no watermark will be advanced.

Design rules:
- badge_id is an INTEGER PK; used as the sole ordering field.
- adoption_rate is DOUBLE in the DWH; coerced to float | None.
- users_awarded is an integer aggregate counter; coerced to int | None.
- No graph logic, canonicalization, or enrichment is applied here.

Source schema:
- Source table  : dim_badges
- Inclusion mode: GRAPH_CORE
- Graph entity  : Badge
- Freshness field: None (static dimension — full refresh on every run)
- Declared PK   : badge_id (INTEGER)
"""

from __future__ import annotations

from app.contracts.warehouse_rows import WarehouseRow
from app.extractors.base import BaseExtractor
from app.schemas.warehouse.badges import (
    FRESHNESS_FIELD,
    INCLUSION_MODE,
    PRIMARY_KEYS,
    SOURCE_NAME,
    BadgesRow,
)


class BadgesExtractor(BaseExtractor):
    """
    Extractor for dim_badges.

    Full-refresh strategy:
    - No timestamp column exists in the DWH; supports_incremental is False.
    - A full table scan is performed on every run. This is correct and cheap
      given the low cardinality of the badge catalog.
    - ordering: badge_id
    """

    source_name: str = SOURCE_NAME
    schema_row_class: type[WarehouseRow] = BadgesRow
    inclusion_mode: str = INCLUSION_MODE
    freshness_field: str | None = FRESHNESS_FIELD       # None — static dimension
    primary_key_fields: tuple[str, ...] = PRIMARY_KEYS
    default_chunk_size: int = 1000
    supports_incremental: bool = False

    # ── Source column contract ────────────────────────────────────────────────

    def get_source_columns(self) -> tuple[str, ...]:
        """
        Return the explicit ordered source columns for dim_badges.

        These columns must stay aligned with BadgesRow.from_row().
        Adding or removing a column here requires a matching change in
        the schema row dataclass.

        adoption_rate note:
            DOUBLE in the DWH; coerced to float | None.
        """
        return (
            "badge_id",
            "badge_name",
            "badge_image",
            "badge_description",
            "users_awarded",
            "adoption_rate",            # DOUBLE in DWH
        )

    # ── Query construction ────────────────────────────────────────────────────

    def build_base_query(self) -> str:
        """
        Return the full SELECT for dim_badges.

        No incremental clause is appended — supports_incremental is False
        and freshness_field is None. The base runtime performs a full table
        scan on every run.
        """
        columns = ",\n    ".join(self.get_source_columns())
        return f"""
SELECT
    {columns}
FROM {self.source_name}
""".strip()

    def build_order_by_clause(self) -> str:
        """
        Return stable deterministic ordering for dim_badges.

        badge_id only — integer PK; fully deterministic across all rows.
        No freshness field exists to lead with on a static dimension.
        """
        return "\nORDER BY badge_id"

    def build_pagination_clause(self, limit: int, offset: int) -> str:
        """
        Return LIMIT/OFFSET pagination clause.
        """
        return "\nLIMIT %(limit)s OFFSET %(offset)s"