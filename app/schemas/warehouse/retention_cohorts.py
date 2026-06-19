"""
Warehouse schema for fct_retention_cohorts.

Source table: fct_retention_cohorts
Domain: ops
Inclusion mode: SERVING_ONLY — feeds cohort retention dashboards
Graph entity: none
Freshness field: cohort_date

Cohort retention analytics. No per-user entity mapping; feeds cohort
dashboards only. No declared PK; composite key (cohort_date_key,
period_weeks_since_cohort) is the stable identifier.

DWH type notes:
    cohort_date_key — INTEGER partition key; str | None.
    cohort_date, period_start, period_end — DATE columns; str | None
        (date-only; no tz coercion).
    retention_rate — DECIMAL(5,2); float | None.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.core.constants import SERVING_ONLY

# ── Module-level constants ────────────────────────────────────────────────────

SOURCE_NAME: str = "fct_retention_cohorts"
INCLUSION_MODE: str = SERVING_ONLY
PRIMARY_KEYS: tuple[str, ...] = ("cohort_date_key", "period_weeks_since_cohort")
FRESHNESS_FIELD: str | None = "cohort_date"
GRAPH_ENTITY_MAPPINGS: tuple[str, ...] = ()


# ── Row shape ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class RetentionCohortsRow:
    """
    Typed row shape for fct_retention_cohorts.

    No single-column PK declared in DWH. The composite key
    (cohort_date_key, period_weeks_since_cohort) is the stable identifier.

    cohort_date_key is an INTEGER partition key; str | None.
    cohort_date, period_start, and period_end are DATE columns; str | None
    (date-only semantics; not converted to datetime).
    retention_rate is DECIMAL(5,2); float | None.
    """

    cohort_size: int | None
    cohort_date_key: str | None
    cohort_date: str | None
    period_weeks_since_cohort: int | None
    period_start: str | None
    period_end: str | None
    active_user_count: int | None
    retention_rate: float | None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> RetentionCohortsRow:
        """Normalize a raw warehouse row into a typed RetentionCohortsRow."""
        return cls(
            cohort_size=int(row["cohort_size"]) if row.get("cohort_size") is not None else None,
            cohort_date_key=str(row["cohort_date_key"]) if row.get("cohort_date_key") is not None else None,
            cohort_date=str(row["cohort_date"]) if row.get("cohort_date") is not None else None,
            period_weeks_since_cohort=int(row["period_weeks_since_cohort"]) if row.get("period_weeks_since_cohort") is not None else None,
            period_start=str(row["period_start"]) if row.get("period_start") is not None else None,
            period_end=str(row["period_end"]) if row.get("period_end") is not None else None,
            active_user_count=int(row["active_user_count"]) if row.get("active_user_count") is not None else None,
            retention_rate=float(row["retention_rate"]) if row.get("retention_rate") is not None else None,
        )
