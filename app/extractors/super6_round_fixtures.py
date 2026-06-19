"""
Extractor for the dim_super6_round_fixtures warehouse source.

Purpose:
- Extract junction rows linking Super6 rounds to their constituent fixtures
  from dim_super6_round_fixtures.
- Full-refresh strategy — the source has no freshness/mutation timestamp,
  so every pipeline run extracts all rows deterministically.
- Return typed Super6RoundFixturesRow instances wrapped in ExtractorBatch.

Source characteristics:
    dim_super6_round_fixtures is a static junction table. Each row asserts
    that a specific fixture is part of a specific Super6 round. Rows are
    written when a round's fixtures are selected and are not updated or
    deleted thereafter — the fixture selection for a round is immutable
    once published.

    Because the table has no timestamp column, incremental extraction is not
    possible and full refresh is the only correct strategy. The table is
    small (six fixtures per round × total round count), so full refresh is
    also efficient.

    HAS_FIXTURE edges (Super6Round → Match) cannot be inferred from either
    parent table alone; this junction is the only source of truth for the
    round-to-fixture mapping.

Design rules:
- All three columns are VARCHAR(100) in the DWH; all preserved as
  str / str | None. The spec suggested int for all three — DWH type wins.
- super6_round_fixture_id is the surrogate PK; preserved for stable row
  identity even though the logical key is the composite
  (super6_round_id, fixture_id).
- super6_round_id and fixture_id are both FKs required for HAS_FIXTURE
  edge construction; neither must be dropped.
- No graph logic, canonicalization, or enrichment is applied here.

Source schema:
- Source table  : dim_super6_round_fixtures
- Inclusion mode: GRAPH_CORE
- Graph entity  : HAS_FIXTURE relationship (Super6Round → Match)
- Freshness field: None (static junction table)
"""

from __future__ import annotations

from app.contracts.warehouse_rows import WarehouseRow
from app.extractors.base import BaseExtractor
from app.schemas.warehouse.super6_round_fixtures import (
    FRESHNESS_FIELD,
    INCLUSION_MODE,
    PRIMARY_KEYS,
    SOURCE_NAME,
    Super6RoundFixturesRow,
)


class Super6RoundFixturesExtractor(BaseExtractor):
    """
    Extractor for dim_super6_round_fixtures.

    Full-refresh strategy:
    - supports_incremental = False
    - freshness_field      = None
    - watermark is never read or written for this source
    - every run extracts the full junction table

    Ordering:
    - super6_round_id, fixture_id — logical composite key ordering;
      groups all fixtures for the same round together and produces
      stable, diff-comparable output across full-refresh runs.
    """

    source_name: str = SOURCE_NAME
    schema_row_class: type[WarehouseRow] = Super6RoundFixturesRow
    inclusion_mode: str = INCLUSION_MODE
    freshness_field: str | None = FRESHNESS_FIELD     # None — static junction
    primary_key_fields: tuple[str, ...] = PRIMARY_KEYS
    default_chunk_size: int = 500                     # very small table;
                                                      # 6 rows per round
    supports_incremental: bool = False

    # ── Source column contract ────────────────────────────────────────────────

    def get_source_columns(self) -> tuple[str, ...]:
        """
        Return the explicit ordered source columns for dim_super6_round_fixtures.

        These columns must stay aligned with Super6RoundFixturesRow.from_row().
        Adding or removing a column here requires a matching change in
        the schema row dataclass.

        Type note:
            All three columns are VARCHAR(100) in the DWH despite the spec
            suggesting int. Preserved as str / str | None; no SQL CAST applied.

        Edge construction note:
            super6_round_id and fixture_id are both required for HAS_FIXTURE
            edge construction. Neither must be dropped or made optional.
        """
        return (
            "super6_round_fixture_id",   # surrogate PK
            "super6_round_id",           # HAS_FIXTURE edge: source node FK
            "fixture_id",                # HAS_FIXTURE edge: target node FK
        )

    # ── Query construction ────────────────────────────────────────────────────

    def build_base_query(self) -> str:
        """
        Return the base SELECT for dim_super6_round_fixtures.

        No WHERE clause is included; the table is always fully refreshed
        because it has no mutation timestamp.
        """
        columns = ",\n    ".join(self.get_source_columns())
        return f"""
SELECT
    {columns}
FROM {self.source_name}
""".strip()

    def build_incremental_clause(self, watermark_value: str | None) -> str:
        """
        Always returns an empty string.

        dim_super6_round_fixtures has no freshness timestamp and is never
        extracted incrementally. This override makes the intent explicit and
        prevents accidental watermark injection during future refactoring.
        """
        return ""

    def build_order_by_clause(self) -> str:
        """
        Return stable deterministic ordering for dim_super6_round_fixtures.

        Ordered by super6_round_id, fixture_id — the logical composite key.
        This groups all fixtures for the same round together and produces
        stable, diff-comparable output across repeated full-refresh runs.
        super6_round_fixture_id is not used as the primary sort because
        surrogate key values are not semantically ordered.
        """
        return "\nORDER BY super6_round_id, fixture_id"

    def build_pagination_clause(self, limit: int, offset: int) -> str:
        """
        Return LIMIT/OFFSET pagination clause.
        """
        return "\nLIMIT %(limit)s OFFSET %(offset)s"