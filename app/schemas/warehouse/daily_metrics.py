"""
Warehouse schema for fct_daily_metrics.

Source table: fct_daily_metrics
Domain: ops
Inclusion mode: SERVING_ONLY — consumed directly by dashboards
Graph entity: none
Freshness field: metric_date

Platform-level aggregate KPIs. No per-user or per-entity node mapping.
Consumed by operational dashboards without graph intermediation.

DWH type notes:
    metric_date — DATE column; str (date-only key used as PK, no tz coercion).
    All DECIMAL columns → float | None.
    calculated_at_utc — DATETIME; datetime | None.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.core.constants import SERVING_ONLY
from app.core.ids import normalize_string_id
from app.core.time import warehouse_value_to_utc_datetime

# ── Module-level constants ────────────────────────────────────────────────────

SOURCE_NAME: str = "fct_daily_metrics"
INCLUSION_MODE: str = SERVING_ONLY
PRIMARY_KEYS: tuple[str, ...] = ("metric_date",)
FRESHNESS_FIELD: str | None = "metric_date"
GRAPH_ENTITY_MAPPINGS: tuple[str, ...] = ()


# ── Row shape ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class DailyMetricsRow:
    """
    Typed row shape for fct_daily_metrics.

    metric_date is a DATE column; stored as str (date-only PK label).
    All ratio/rate/financial fields are DECIMAL; float | None.
    """

    metric_date: str
    total_users: int | None
    new_signups: int | None
    active_users_today: int | None
    active_users_7d: int | None
    active_users_30d: int | None
    dau_mau_ratio: float | None
    total_predictions_today: int | None
    total_posts_today: int | None
    total_comments_today: int | None
    total_quiz_attempts_today: int | None
    avg_predictions_per_active_user: float | None
    avg_posts_per_active_user: float | None
    engagement_rate: float | None
    new_subscriptions_today: int | None
    active_subscriptions: int | None
    churned_subscriptions_today: int | None
    mrr: float | None
    arr: float | None
    churn_rate: float | None
    signups_change_vs_yesterday: int | None
    dau_change_vs_yesterday: int | None
    mrr_change_vs_yesterday: float | None
    calculated_at_utc: datetime | None
    active_chat_users: int | None
    active_session_users: int | None
    revenue_new: float | None
    revenue_renewal: float | None
    payments_volume: float | None
    active_users_7d_weekly: int | None
    wau_change_vs_last_week: int | None
    returning_users_today: int | None
    retention_rate_day1: float | None
    retention_rate_day7: float | None
    retention_rate_day30: float | None
    wau: int | None
    returning_users_7d: int | None
    returning_users_30d: int | None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> DailyMetricsRow:
        """Normalize a raw warehouse row into a typed DailyMetricsRow."""
        return cls(
            metric_date=str(normalize_string_id(row["metric_date"], field_name="metric_date")),
            total_users=int(row["total_users"]) if row.get("total_users") is not None else None,
            new_signups=int(row["new_signups"]) if row.get("new_signups") is not None else None,
            active_users_today=int(row["active_users_today"]) if row.get("active_users_today") is not None else None,
            active_users_7d=int(row["active_users_7d"]) if row.get("active_users_7d") is not None else None,
            active_users_30d=int(row["active_users_30d"]) if row.get("active_users_30d") is not None else None,
            dau_mau_ratio=float(row["dau_mau_ratio"]) if row.get("dau_mau_ratio") is not None else None,
            total_predictions_today=int(row["total_predictions_today"]) if row.get("total_predictions_today") is not None else None,
            total_posts_today=int(row["total_posts_today"]) if row.get("total_posts_today") is not None else None,
            total_comments_today=int(row["total_comments_today"]) if row.get("total_comments_today") is not None else None,
            total_quiz_attempts_today=int(row["total_quiz_attempts_today"]) if row.get("total_quiz_attempts_today") is not None else None,
            avg_predictions_per_active_user=float(row["avg_predictions_per_active_user"]) if row.get("avg_predictions_per_active_user") is not None else None,
            avg_posts_per_active_user=float(row["avg_posts_per_active_user"]) if row.get("avg_posts_per_active_user") is not None else None,
            engagement_rate=float(row["engagement_rate"]) if row.get("engagement_rate") is not None else None,
            new_subscriptions_today=int(row["new_subscriptions_today"]) if row.get("new_subscriptions_today") is not None else None,
            active_subscriptions=int(row["active_subscriptions"]) if row.get("active_subscriptions") is not None else None,
            churned_subscriptions_today=int(row["churned_subscriptions_today"]) if row.get("churned_subscriptions_today") is not None else None,
            mrr=float(row["mrr"]) if row.get("mrr") is not None else None,
            arr=float(row["arr"]) if row.get("arr") is not None else None,
            churn_rate=float(row["churn_rate"]) if row.get("churn_rate") is not None else None,
            signups_change_vs_yesterday=int(row["signups_change_vs_yesterday"]) if row.get("signups_change_vs_yesterday") is not None else None,
            dau_change_vs_yesterday=int(row["dau_change_vs_yesterday"]) if row.get("dau_change_vs_yesterday") is not None else None,
            mrr_change_vs_yesterday=float(row["mrr_change_vs_yesterday"]) if row.get("mrr_change_vs_yesterday") is not None else None,
            calculated_at_utc=warehouse_value_to_utc_datetime(row.get("calculated_at_utc")),
            active_chat_users=int(row["active_chat_users"]) if row.get("active_chat_users") is not None else None,
            active_session_users=int(row["active_session_users"]) if row.get("active_session_users") is not None else None,
            revenue_new=float(row["revenue_new"]) if row.get("revenue_new") is not None else None,
            revenue_renewal=float(row["revenue_renewal"]) if row.get("revenue_renewal") is not None else None,
            payments_volume=float(row["payments_volume"]) if row.get("payments_volume") is not None else None,
            active_users_7d_weekly=int(row["active_users_7d_weekly"]) if row.get("active_users_7d_weekly") is not None else None,
            wau_change_vs_last_week=int(row["wau_change_vs_last_week"]) if row.get("wau_change_vs_last_week") is not None else None,
            returning_users_today=int(row["returning_users_today"]) if row.get("returning_users_today") is not None else None,
            retention_rate_day1=float(row["retention_rate_day1"]) if row.get("retention_rate_day1") is not None else None,
            retention_rate_day7=float(row["retention_rate_day7"]) if row.get("retention_rate_day7") is not None else None,
            retention_rate_day30=float(row["retention_rate_day30"]) if row.get("retention_rate_day30") is not None else None,
            wau=int(row["wau"]) if row.get("wau") is not None else None,
            returning_users_7d=int(row["returning_users_7d"]) if row.get("returning_users_7d") is not None else None,
            returning_users_30d=int(row["returning_users_30d"]) if row.get("returning_users_30d") is not None else None,
        )
