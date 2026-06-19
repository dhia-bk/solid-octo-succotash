"""
Extractor for the dim_avatars warehouse source.

Purpose:
- Extract avatar catalog rows from dim_avatars, including identity, name,
  image URL, description, unlock count, and adoption rate.
- Full-refresh strategy on every run — no timestamp column exists in the DWH.
- Return typed AvatarsRow instances wrapped in ExtractorBatch.

Full-refresh strategy:
    dim_avatars is a static dimension — the avatar catalog changes
    infrequently and carries no timestamp column in the DWH. There is no
    basis for incremental filtering; every run performs a full table scan.
    The table is expected to be small, so full-refresh overhead is negligible.

    supports_incremental is False and freshness_field is None. The base
    runtime will emit no incremental clause and no watermark will be
    advanced or persisted for this source.

Design rules:
- avatar_id is an INTEGER PK in the DWH; extracted as int.
- adoption_rate is DOUBLE in the DWH; coerced to float | None.
- No graph logic, canonicalization, or enrichment is applied here.

Source schema:
- Source table  : dim_avatars
- Inclusion mode: GRAPH_CORE
- Graph entity  : Avatar
- Freshness field: None (static dimension — full refresh every run)
- Declared PK   : avatar_id (INTEGER)
"""

from __future__ import annotations

from app.contracts.warehouse_rows import WarehouseRow
from app.extractors.base import BaseExtractor
from app.schemas.warehouse.avatars import (
    INCLUSION_MODE,
    PRIMARY_KEYS,
    SOURCE_NAME,
    AvatarsRow,
)


class AvatarsExtractor(BaseExtractor):
    """
    Extractor for dim_avatars.

    Full-refresh strategy:
    - No timestamp column in the DWH; supports_incremental is False.
    - freshness_field is None; no incremental clause is emitted.
    - Every run performs a complete table scan. Table volume is expected to
      be small, making full-refresh overhead negligible.
    - ordering: avatar_id
    """

    source_name: str = SOURCE_NAME
    schema_row_class: type[WarehouseRow] = AvatarsRow
    inclusion_mode: str = INCLUSION_MODE
    freshness_field: str | None = None
    primary_key_fields: tuple[str, ...] = PRIMARY_KEYS
    default_chunk_size: int = 1000
    supports_incremental: bool = False

    # ── Source column contract ────────────────────────────────────────────────

    def get_source_columns(self) -> tuple[str, ...]:
        """
        Return the explicit ordered source columns for dim_avatars.

        These columns must stay aligned with AvatarsRow.from_row().
        Adding or removing a column here requires a matching change in
        the schema row dataclass.

        adoption_rate note:
            DOUBLE in the DWH; coerced to float | None.
        """
        return (
            "avatar_id",
            "avatar_name",
            "avatar_image",
            "avatar_description",
            "users_unlocked",
            "adoption_rate",            # DOUBLE in DWH
        )

    # ── Query construction ────────────────────────────────────────────────────

    def build_base_query(self) -> str:
        """
        Return the base SELECT for dim_avatars.

        No incremental clause is appended — supports_incremental is False
        and freshness_field is None. Every call performs a full table scan.
        """
        columns = ",\n    ".join(self.get_source_columns())
        return f"""
SELECT
    {columns}
FROM {self.source_name}
""".strip()

    def build_order_by_clause(self) -> str:
        """
        Return stable deterministic ordering for dim_avatars.

        avatar_id only — integer PK; fully deterministic across all rows
        with no tiebreaker required.
        """
        return "\nORDER BY avatar_id"

    def build_pagination_clause(self, limit: int, offset: int) -> str:
        """
        Return LIMIT/OFFSET pagination clause.
        """
        return "\nLIMIT %(limit)s OFFSET %(offset)s"