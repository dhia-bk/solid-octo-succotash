"""
Serving view / materialization validation.

Checks that user-facing read paths have fresh, complete, and populated data.
All checks are read-only; nothing is written to the graph.
"""

from __future__ import annotations

from typing import Any

from app.core.constants import CURRENT_STATE, PERSONA_STATE, USER
from app.core.time import utc_now
from app.db.neo4j_client import Neo4jClient
from app.validation.base import BaseValidator, ValidationResult, ValidationSeverity


class ServingValidator(BaseValidator):
    """Validates serving view materialization completeness and staleness."""

    def __init__(self, run_id: str, neo4j_client: Neo4jClient) -> None:
        super().__init__(run_id)
        self._client = neo4j_client

    def validate(self, *args: Any, **kwargs: Any) -> list[ValidationResult]:
        raise NotImplementedError(
            "Use specific check methods on ServingValidator directly."
        )

    def check_user_features_materialized(
        self, expected_user_count: int,
    ) -> ValidationResult:
        """WARNING if users with materialized feature vectors are > 5% below expected."""
        name = "check_user_features_materialized"
        query = (
            f"MATCH (n:{USER}) WHERE n.feature_vector IS NOT NULL "
            "RETURN count(n) AS materialized_count"
        )
        try:
            records = self._client.query_many(query)
            materialized = records[0]["materialized_count"] if records else 0
        except Exception as exc:
            return self._fail(name, USER, ValidationSeverity.ERROR,
                              f"Query failed while checking feature materialization: {exc}",
                              expected_user_count=expected_user_count)

        if expected_user_count == 0:
            return self._pass(name, USER, "No expected users — skipping coverage check")

        coverage = materialized / expected_user_count
        if coverage >= 0.95:
            return self._pass(name, USER,
                              f"Feature vectors materialized for {coverage:.1%} of users",
                              materialized=materialized,
                              expected=expected_user_count,
                              coverage_pct=round(coverage, 4))
        return self._warn(name, USER,
                          f"Only {coverage:.1%} of users have materialized feature vectors "
                          f"(expected >= 95%)",
                          materialized=materialized,
                          expected=expected_user_count,
                          coverage_pct=round(coverage, 4))

    def check_tribe_summaries_fresh(self, max_age_hours: int = 24) -> ValidationResult:
        """WARNING if any tribe summary node has updated_at older than max_age_hours."""
        name = "check_tribe_summaries_fresh"
        cutoff = utc_now().timestamp() - (max_age_hours * 3600)
        query = (
            "MATCH (n:TribeSummary) WHERE n.updated_at IS NOT NULL "
            "WITH n, datetime(n.updated_at).epochSeconds AS ts "
            f"WHERE ts < {cutoff} "
            "RETURN count(n) AS stale_count"
        )
        try:
            records = self._client.query_many(query)
            stale_count = records[0]["stale_count"] if records else 0
        except Exception as exc:
            return self._fail(name, "TribeSummary", ValidationSeverity.ERROR,
                              f"Query failed while checking tribe summary freshness: {exc}",
                              max_age_hours=max_age_hours)

        if stale_count == 0:
            return self._pass(name, "TribeSummary",
                              f"All tribe summaries are within {max_age_hours}h",
                              max_age_hours=max_age_hours)
        return self._warn(name, "TribeSummary",
                          f"{stale_count} tribe summary node(s) are older than {max_age_hours}h",
                          stale_count=stale_count, max_age_hours=max_age_hours)

    def check_persona_states_current(self, expected_user_count: int) -> ValidationResult:
        """WARNING if fewer than 90% of active users have a CURRENT_STATE PersonaState."""
        name = "check_persona_states_current"
        query = (
            f"MATCH (u:{USER})-[:{CURRENT_STATE}]->(:{PERSONA_STATE}) "
            "RETURN count(u) AS linked_count"
        )
        try:
            records = self._client.query_many(query)
            linked_count = records[0]["linked_count"] if records else 0
        except Exception as exc:
            return self._fail(name, USER, ValidationSeverity.ERROR,
                              f"Query failed while checking persona state links: {exc}",
                              expected_user_count=expected_user_count)

        if expected_user_count == 0:
            return self._pass(name, USER, "No expected users — skipping persona state check")

        coverage = linked_count / expected_user_count
        if coverage >= 0.90:
            return self._pass(name, USER,
                              f"{coverage:.1%} of users have a CURRENT_STATE PersonaState",
                              linked_count=linked_count,
                              expected=expected_user_count)
        return self._warn(name, USER,
                          f"Only {coverage:.1%} of users have a CURRENT_STATE PersonaState "
                          f"(expected >= 90%)",
                          linked_count=linked_count,
                          expected=expected_user_count,
                          coverage_pct=round(coverage, 4))

    def check_serving_view_completeness(
        self,
        view_label: str,
        min_coverage_pct: float = 0.95,
    ) -> ValidationResult:
        """WARNING if serving view coverage is below min_coverage_pct."""
        name = "check_serving_view_completeness"
        query = (
            f"MATCH (n:{view_label}) "
            "RETURN count(n) AS total, "
            "count(n.serving_ready) AS ready_count"
        )
        try:
            records = self._client.query_many(query)
            row = records[0] if records else {"total": 0, "ready_count": 0}
            total = row["total"]
            ready_count = row["ready_count"]
        except Exception as exc:
            return self._fail(name, view_label, ValidationSeverity.ERROR,
                              f"Query failed while checking serving view completeness: {exc}",
                              view_label=view_label)

        if total == 0:
            return self._pass(name, view_label,
                              f"No {view_label} nodes found — skipping coverage check")

        coverage = ready_count / total
        if coverage >= min_coverage_pct:
            return self._pass(name, view_label,
                              f"{coverage:.1%} of {view_label} nodes are serving-ready",
                              coverage_pct=round(coverage, 4), total=total)
        return self._warn(name, view_label,
                          f"Serving view coverage {coverage:.1%} is below "
                          f"min {min_coverage_pct:.1%}",
                          coverage_pct=round(coverage, 4),
                          total=total,
                          ready_count=ready_count,
                          min_coverage_pct=min_coverage_pct)

    def check_no_stale_inference_results(
        self, max_age_hours: int = 48,
    ) -> ValidationResult:
        """WARNING if any inference output nodes have calculated_at older than max_age_hours."""
        name = "check_no_stale_inference_results"
        cutoff = utc_now().timestamp() - (max_age_hours * 3600)
        query = (
            f"MATCH (n:{PERSONA_STATE}) WHERE n.calculated_at IS NOT NULL "
            "WITH n, datetime(n.calculated_at).epochSeconds AS ts "
            f"WHERE ts < {cutoff} "
            "RETURN count(n) AS stale_count"
        )
        try:
            records = self._client.query_many(query)
            stale_count = records[0]["stale_count"] if records else 0
        except Exception as exc:
            return self._fail(name, PERSONA_STATE, ValidationSeverity.ERROR,
                              f"Query failed while checking inference result staleness: {exc}",
                              max_age_hours=max_age_hours)

        if stale_count == 0:
            return self._pass(name, PERSONA_STATE,
                              f"All inference results are within {max_age_hours}h",
                              max_age_hours=max_age_hours)
        return self._warn(name, PERSONA_STATE,
                          f"{stale_count} inference node(s) have calculated_at "
                          f"older than {max_age_hours}h",
                          stale_count=stale_count, max_age_hours=max_age_hours)

    def check_notification_feature_freshness(
        self, max_age_hours: int = 6,
    ) -> ValidationResult:
        """WARNING if notification feature vectors have not refreshed within max_age_hours."""
        name = "check_notification_feature_freshness"
        cutoff = utc_now().timestamp() - (max_age_hours * 3600)
        query = (
            f"MATCH (n:{USER}) WHERE n.notification_feature_updated_at IS NOT NULL "
            "WITH n, datetime(n.notification_feature_updated_at).epochSeconds AS ts "
            f"WHERE ts < {cutoff} "
            "RETURN count(n) AS stale_count"
        )
        try:
            records = self._client.query_many(query)
            stale_count = records[0]["stale_count"] if records else 0
        except Exception as exc:
            return self._fail(name, USER, ValidationSeverity.ERROR,
                              f"Query failed while checking notification feature freshness: {exc}",
                              max_age_hours=max_age_hours)

        if stale_count == 0:
            return self._pass(name, USER,
                              f"Notification features refreshed within {max_age_hours}h",
                              max_age_hours=max_age_hours)
        return self._warn(name, USER,
                          f"{stale_count} user(s) have stale notification features "
                          f"(> {max_age_hours}h old)",
                          stale_count=stale_count, max_age_hours=max_age_hours)