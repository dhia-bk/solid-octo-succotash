"""
Warehouse schema for dim_super6_round_fixtures.

Source table: dim_super6_round_fixtures
Domain: competition
Inclusion mode: GRAPH_CORE — feeds relationship creation
Graph entity: HAS_FIXTURE relationship (Super6Round → Match)
Freshness field: None (static junction table — full refresh on every run)

Junction table linking each Super6 round to its six constituent fixtures.
Required to build HAS_FIXTURE edges; cannot be inferred from either parent.

DWH type note:
    All three columns are VARCHAR(100) in the DWH. The spec suggested int
    for all three — DWH wins.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.core.constants import GRAPH_CORE, HAS_FIXTURE
from app.core.ids import normalize_nullable_string_id, normalize_string_id

# ── Module-level constants ────────────────────────────────────────────────────

SOURCE_NAME: str = "dim_super6_round_fixtures"
INCLUSION_MODE: str = GRAPH_CORE
PRIMARY_KEYS: tuple[str, ...] = ("super6_round_fixture_id",)
FRESHNESS_FIELD: str | None = None
GRAPH_ENTITY_MAPPINGS: tuple[str, ...] = (HAS_FIXTURE,)


# ── Row shape ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Super6RoundFixturesRow:
    """
    Typed row shape for dim_super6_round_fixtures.

    All three columns are VARCHAR(100) in the DWH; stored as str / str | None.
    """

    super6_round_fixture_id: str
    super6_round_id: str | None
    fixture_id: str | None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> Super6RoundFixturesRow:
        """Normalize a raw warehouse row into a typed Super6RoundFixturesRow."""
        return cls(
            super6_round_fixture_id=normalize_string_id(row["super6_round_fixture_id"], field_name="super6_round_fixture_id"),
            super6_round_id=normalize_nullable_string_id(row.get("super6_round_id"), field_name="super6_round_id"),
            fixture_id=normalize_nullable_string_id(row.get("fixture_id"), field_name="fixture_id"),
        )
