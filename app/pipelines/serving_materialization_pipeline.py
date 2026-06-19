"""
Serving materialization pipeline — refreshes serving views after analytics jobs.

Runs after the analytics layer (Stage 13) outputs tribe assignments, PageRank
scores, and inference results have been written to the graph.

Triggers:
- AnalyticsLoader serving-view writers (tribe summaries, persona nodes, feature vectors)
- ServingValidator post-materialization checks

Not a BasePipeline subclass — no warehouse source extraction involved.
"""

from __future__ import annotations

from time import perf_counter

from app.core.constants import SERVING_MATERIALIZATION_PIPELINE
from app.core.logging import get_logger, log_event
from app.core.time import utc_now
from app.loaders.analytics_loader import AnalyticsLoader
from app.pipelines.base import PipelineContext, PipelineResult
from app.validation.serving_checks import ServingValidator

LOGGER = get_logger(__name__)

_AUDIT_NODE_QUERY = """\
MERGE (sm:ServingMaterializationRun {id: $run_id})
SET sm.ran_at = datetime(),
    sm.status = $status,
    sm._updated_at = $ran_at"""

_USER_COUNT_QUERY = "MATCH (u:User) RETURN count(u) AS total"


class ServingMaterializationPipeline:
    """
    Refreshes serving-layer graph structures after analytics jobs complete.

    Triggers analytics_loader write methods to materialise tribe summaries,
    persona serving nodes, and user feature vectors, then runs serving checks.
    """

    def __init__(
        self,
        context: PipelineContext,
    ) -> None:
        self._context = context
        self._run_id = context.run_id
        self._neo4j_client = context.neo4j_client
        self._dry_run = context.dry_run
        self._logger = get_logger(__name__, run_id=context.run_id)

    def run(self) -> PipelineResult:
        started = perf_counter()
        started_at = utc_now().isoformat()
        result = PipelineResult(
            pipeline_name=SERVING_MATERIALIZATION_PIPELINE,
            run_id=self._run_id,
            status="failed",
            started_at=started_at,
        )

        log_event(
            self._logger,
            "serving_materialization_started",
            run_id=self._run_id,
            dry_run=self._dry_run,
        )

        try:
            analytics_loader = AnalyticsLoader(
                neo4j_client=self._neo4j_client,
                run_id=self._run_id,
                dry_run=self._dry_run,
            )
            serving_validator = ServingValidator(
                run_id=self._run_id,
                neo4j_client=self._neo4j_client,
            )

            if not self._dry_run:
                # 1. Check analytics coverage before materializing
                tribe_coverage = self._check_analytics_coverage(analytics_loader)
                log_event(
                    self._logger,
                    "analytics_coverage_checked",
                    tribe_coverage=tribe_coverage,
                    run_id=self._run_id,
                )

                # 2. Trigger serving view refresh
                analytics_loader.write_tribe_summaries()
                analytics_loader.write_persona_serving_nodes()
                analytics_loader.write_user_feature_vectors()

                # 3. Post-materialization validation
                user_count = self._get_user_count()
                validation_results = [
                    serving_validator.check_user_features_materialized(user_count),
                    serving_validator.check_tribe_summaries_fresh(),
                    serving_validator.check_persona_states_current(),
                ]
                result.validation_failures = sum(
                    1 for r in validation_results if not r.passed
                )

                # 4. Audit node
                self._write_audit_node(status="completed")

            result.status = "dry_run" if self._dry_run else "completed"

        except Exception as exc:
            result.status = "failed"
            result.error_messages.append(str(exc))
            log_event(
                self._logger,
                "serving_materialization_error",
                error=str(exc),
                run_id=self._run_id,
            )
            try:
                self._write_audit_node(status="failed")
            except Exception:
                pass

        finally:
            result.finished_at = utc_now().isoformat()
            result.duration_seconds = perf_counter() - started
            log_event(
                self._logger,
                "serving_materialization_finished",
                run_id=self._run_id,
                status=result.status,
                duration_seconds=result.duration_seconds,
            )

        return result

    def _check_analytics_coverage(self, analytics_loader: AnalyticsLoader) -> dict:
        """Best-effort check of tribe_id and pagerank_score coverage before materializing."""
        try:
            tribe_query = (
                "MATCH (u:User) WHERE u.tribe_id IS NOT NULL "
                "RETURN count(u) AS tribe_count"
            )
            pagerank_query = (
                "MATCH (u:User) WHERE u.pagerank_score IS NOT NULL "
                "RETURN count(u) AS pr_count"
            )
            tribe_records = self._neo4j_client.query_many(tribe_query)
            pr_records = self._neo4j_client.query_many(pagerank_query)
            return {
                "tribe_count": tribe_records[0]["tribe_count"] if tribe_records else 0,
                "pagerank_count": pr_records[0]["pr_count"] if pr_records else 0,
            }
        except Exception as exc:
            log_event(self._logger, "analytics_coverage_check_error", error=str(exc))
            return {}

    def _get_user_count(self) -> int:
        try:
            records = self._neo4j_client.query_many(_USER_COUNT_QUERY)
            return records[0]["total"] if records else 0
        except Exception:
            return 0

    def _write_audit_node(self, status: str) -> None:
        try:
            self._neo4j_client.run_write(
                _AUDIT_NODE_QUERY,
                {
                    "run_id": self._run_id,
                    "status": status,
                    "ran_at": utc_now().isoformat(),
                },
            )
        except Exception as exc:
            log_event(self._logger, "serving_audit_node_error", error=str(exc))
