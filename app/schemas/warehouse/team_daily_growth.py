"""
Warehouse schema for fct_team_daily_growth.

Source table: fct_team_daily_growth
Domain: ops
Inclusion mode: FEATURE_SOURCE — feeds team analytics model features
Graph entity: none
Freshness field: metric_date

Team-level fan growth time series. No per-user entity mapping; no declared
PK in DWH; composite key (metric_date, team_id) is the stable identifier.

DWH type notes:
    team_id         — VARCHAR(100) in DWH; str | None (spec suggested int).
    metric_date     — DATE column; str | None (date-only; no tz coercion).
    metric_date_key — INTEGER partition key; str | None.
    growth_rate_pct — DECIMAL(5,2); float | None.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.core.constants import FEATURE_SOURCE
from app.core.ids import normalize_nullable_string_id
from app.core.time import warehouse_value_to_utc_datetime

# ── Module-level constants ────────────────────────────────────────────────────

SOURCE_NAME: str = "fct_team_daily_growth"
INCLUSION_MODE: str = FEATURE_SOURCE
PRIMARY_KEYS: tuple[str, ...] = ("metric_date", "team_id")
FRESHNESS_FIELD: str | None = "metric_date"
GRAPH_ENTITY_MAPPINGS: tuple[str, ...] = ()


# ── Row shape ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class TeamDailyGrowthRow:
    """
    Typed row shape for fct_team_daily_growth.

    No single-column PK declared in DWH. The composite key
    (metric_date, team_id) is the stable identifier.

    team_id is VARCHAR(100) in the DWH; str | None.
    metric_date is a DATE column; str | None (date-only label).
    metric_date_key is an INTEGER partition key; str | None.
    growth_rate_pct is DECIMAL(5,2); float | None.
    """

    metric_date: str | None
    team_id: str | None
    team_name: str | None
    new_fans_today: int | None
    total_fans: int | None
    fans_lost_today: int | None
    net_fan_change: int | None
    growth_rate_pct: float | None
    metric_date_key: str | None
    calculated_at_utc: datetime | None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> TeamDailyGrowthRow:
        """Normalize a raw warehouse row into a typed TeamDailyGrowthRow."""
        return cls(
            metric_date=str(row["metric_date"]) if row.get("metric_date") is not None else None,
            team_id=normalize_nullable_string_id(row.get("team_id"), field_name="team_id"),
            team_name=row.get("team_name"),
            new_fans_today=int(row["new_fans_today"]) if row.get("new_fans_today") is not None else None,
            total_fans=int(row["total_fans"]) if row.get("total_fans") is not None else None,
            fans_lost_today=int(row["fans_lost_today"]) if row.get("fans_lost_today") is not None else None,
            net_fan_change=int(row["net_fan_change"]) if row.get("net_fan_change") is not None else None,
            growth_rate_pct=float(row["growth_rate_pct"]) if row.get("growth_rate_pct") is not None else None,
            metric_date_key=str(row["metric_date_key"]) if row.get("metric_date_key") is not None else None,
            calculated_at_utc=warehouse_value_to_utc_datetime(row.get("calculated_at_utc")),
        )
