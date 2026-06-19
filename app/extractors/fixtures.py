"""
Extractor for the dim_fixtures warehouse source.

Purpose:
- Extract the central match backbone from dim_fixtures.
- Dual-mode extraction: bounded active-window sync (default) for pipeline
  runs, or unbounded backfill mode for historical loads.
- Return typed FixturesRow instances wrapped in ExtractorBatch.

Extraction modes
────────────────
ACTIVE_WINDOW (default):
    Filters kickoff_at_utc to a rolling window centred on now:
        kickoff_at_utc >= NOW() - lookback_days
        AND kickoff_at_utc <= NOW() + lookahead_days
    This keeps each pipeline run fast and focused on the commercially
    relevant fixture window (recent results + upcoming matches).
    The watermark is still advanced so downstream stages know the last
    processed point, but the primary filter is the rolling window, not
    a watermark lower-bound. This is intentional: a fixture's status,
    score, elapsed_time, and prediction_count all mutate after kickoff,
    so any fixture within the active window must be re-extracted on
    every run regardless of when it was last seen.

BACKFILL:
    Standard watermark-based incremental — extracts all rows where
    kickoff_at_utc > last watermark. Used for historical season loads
    and pipeline recovery. The caller is responsible for setting an
    appropriate starting watermark (or None for a full initial load).

Design rules:
- fixture_id, home_team_id, and away_team_id are all VARCHAR in the DWH
  and are preserved as strings here. team_id type reconciliation against
  dim_teams (also VARCHAR) and dim_teams_enhanced (INTEGER) belongs to
  the transformer layer.
- kickoff_date_key is an INTEGER partition label in the DWH; LeaguesRow
  stores it as str | None. No numeric arithmetic should be applied to it.
- No graph logic, canonicalization, or enrichment is applied here.

Source schema:
- Source table  : dim_fixtures
- Inclusion mode: GRAPH_CORE
- Graph entity  : Match
- Freshness field: kickoff_at_utc
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.contracts.warehouse_rows import WarehouseRow
from app.extractors.base import BaseExtractor
from app.schemas.warehouse.fixtures import (
    FRESHNESS_FIELD,
    INCLUSION_MODE,
    PRIMARY_KEYS,
    SOURCE_NAME,
    FixturesRow,
)

# ── Extraction mode constants ─────────────────────────────────────────────────

ACTIVE_WINDOW: str = "active_window"
BACKFILL: str = "backfill"

DEFAULT_LOOKBACK_DAYS: int = 14
DEFAULT_LOOKAHEAD_DAYS: int = 7


class FixturesExtractor(BaseExtractor):
    """
    Extractor for dim_fixtures.

    Active-window mode (default):
    - Extracts fixtures where kickoff_at_utc is within a rolling window.
    - Window bounds are computed fresh on every run (not from a checkpoint).
    - Default window: 14 days back to 7 days forward from UTC now.
    - Watermark is still advanced to the max kickoff_at_utc in the batch
      so downstream stages have a consistent reference point.

    Backfill mode:
    - Standard watermark-based incremental.
    - Extracts all rows where kickoff_at_utc > last watermark.
    - First run (no watermark) → full historical load.
    - Use for season bootstraps, pipeline recovery, and data corrections.

    Ordering:
    - kickoff_at_utc, fixture_id — deterministic across both modes, and
      naturally aligns with how prediction and discussion tables join.
    """

    source_name: str = SOURCE_NAME
    schema_row_class: type[WarehouseRow] = FixturesRow
    inclusion_mode: str = INCLUSION_MODE
    freshness_field: str | None = FRESHNESS_FIELD     # kickoff_at_utc
    primary_key_fields: tuple[str, ...] = PRIMARY_KEYS
    default_chunk_size: int = 2000                    # fixtures can be large
                                                      # on historical backfills
    supports_incremental: bool = True

    def __init__(
        self,
        mysql_client,
        *,
        chunk_size: int | None = None,
        extraction_mode: str = ACTIVE_WINDOW,
        lookback_days: int = DEFAULT_LOOKBACK_DAYS,
        lookahead_days: int = DEFAULT_LOOKAHEAD_DAYS,
    ) -> None:
        """
        Initialise the fixtures extractor.

        Args:
            mysql_client:
                Injected MySQLClient instance (required by BaseExtractor).
            chunk_size:
                Override the default chunk size for this run.
            extraction_mode:
                ACTIVE_WINDOW (default) or BACKFILL. Controls which SQL
                filter strategy is applied via build_incremental_clause().
            lookback_days:
                Active-window mode only. How many days before UTC now to
                set the lower kickoff_at_utc bound. Default: 14 days.
            lookahead_days:
                Active-window mode only. How many days after UTC now to
                set the upper kickoff_at_utc bound. Default: 7 days.
        """
        if extraction_mode not in (ACTIVE_WINDOW, BACKFILL):
            raise ValueError(
                f"extraction_mode must be {ACTIVE_WINDOW!r} or {BACKFILL!r}; "
                f"got {extraction_mode!r}"
            )

        self.extraction_mode = extraction_mode
        self.lookback_days = lookback_days
        self.lookahead_days = lookahead_days

        super().__init__(mysql_client, chunk_size=chunk_size)

    # ── Source column contract ────────────────────────────────────────────────

    def get_source_columns(self) -> tuple[str, ...]:
        """
        Return the explicit ordered source columns for dim_fixtures.

        These columns must stay aligned with FixturesRow.from_row().
        Adding or removing a column here requires a matching change in
        the schema row dataclass.

        Cross-source FK notes preserved at extraction:
            league_id   — FK to dim_leagues (integer); preserved as-is.
            home_team_id / away_team_id — VARCHAR FKs matching dim_teams.
                          dim_teams_enhanced uses integer team_id; the
                          transformer resolves the type mismatch, not here.
        """
        return (
            "fixture_id",
            "away_team_logo",
            "away_team_name",
            "country",
            "country_flag",
            "elapsed_time",
            "extra_time_score",
            "final_game_score",
            "home_team_logo",
            "home_team_name",
            "kickoff_at_utc",
            "league_id",
            "league_logo",
            "league_name",
            "penalty_score",
            "season",
            "status",
            "kickoff_date_key",
            "home_team_id",
            "away_team_id",
            "public_prediction_count",
            "private_prediction_count",
            "has_discussion",
            "result_known",
            "fixture_era",
        )

    # ── Query construction ────────────────────────────────────────────────────

    def build_base_query(self) -> str:
        """
        Return the base SELECT for dim_fixtures without filter clauses.

        The appropriate filter (active-window bounds or watermark) is
        appended by the base runtime via build_incremental_clause().
        """
        columns = ",\n    ".join(self.get_source_columns())
        return f"""
SELECT
    {columns}
FROM {self.source_name}
""".strip()

    def build_incremental_clause(self, watermark_value: str | None) -> str:
        """
        Build the extraction filter clause based on the configured mode.

        Active-window mode:
            WHERE kickoff_at_utc >= %(window_lower)s
              AND kickoff_at_utc <= %(window_upper)s

            Window bounds are computed at call time from UTC now.
            The watermark_value parameter is intentionally ignored in this
            mode — active-window extraction is time-centred, not watermark-
            driven. Fixtures within the window must always be re-extracted
            because status, score, and prediction counts mutate after kickoff.

        Backfill mode:
            WHERE kickoff_at_utc > %(watermark_value)s   (if watermark set)
            [no clause]                                   (first run / full load)

            Standard monotonic watermark incremental. Uses %(watermark_value)s
            so the base runtime's _build_query_params() populates the value.
        """
        if self.extraction_mode == ACTIVE_WINDOW:
            return self._build_active_window_clause()

        # BACKFILL mode — standard watermark filter
        if not self.supports_incremental or not self.freshness_field:
            return ""
        if not watermark_value:
            return ""
        return f"\nWHERE {self.freshness_field} > %(watermark_value)s"

    def _build_active_window_clause(self) -> str:
        """
        Return the rolling time-window WHERE clause for active-window mode.

        Bounds are formatted as ISO 8601 strings compatible with MySQL
        DATETIME comparison. The clause uses named literals (not %(params)s)
        because the window bounds are computed here and do not flow through
        the base runtime's _build_query_params() dict.
        """
        now_utc = datetime.now(tz=timezone.utc)
        lower = now_utc - timedelta(days=self.lookback_days)
        upper = now_utc + timedelta(days=self.lookahead_days)

        lower_str = lower.strftime("%Y-%m-%d %H:%M:%S")
        upper_str = upper.strftime("%Y-%m-%d %H:%M:%S")

        return (
            f"\nWHERE {self.freshness_field} >= '{lower_str}'"
            f"\n  AND {self.freshness_field} <= '{upper_str}'"
        )

    def build_order_by_clause(self) -> str:
        """
        Return stable deterministic ordering for dim_fixtures.

        kickoff_at_utc first — aligns with how prediction, discussion, and
        duel tables join on fixture time, and clusters output naturally for
        the most common downstream access pattern.

        fixture_id second — breaks ties (multiple fixtures at the same UTC
        second, which can happen in live data warehouses) deterministically.
        """
        return "\nORDER BY kickoff_at_utc, fixture_id"

    def build_pagination_clause(self, limit: int, offset: int) -> str:
        """
        Return LIMIT/OFFSET pagination clause.
        """
        return "\nLIMIT %(limit)s OFFSET %(offset)s"