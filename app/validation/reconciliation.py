"""
Source-to-graph reconciliation validation.

Detects missing loads, duplicate runs, and unexpected count drift between
warehouse row counts and what landed in the graph.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.contracts.graph_records import GraphWriteBatch
from app.db.checkpoints import CheckpointRepository
from app.db.job_runs import JobRunRepository
from app.db.neo4j_client import Neo4jClient
from app.validation.assertions import assert_count_within_threshold
from app.validation.base import BaseValidator, ValidationResult, ValidationSeverity


@dataclass
class ReconciliationReport:
    source_name: str
    run_id: str
    warehouse_row_count: int
    graph_node_count: int | None
    graph_rel_count: int | None
    expected_skip_count: int
    effective_load_count: int
    drift_pct: float
    within_threshold: bool
    results: list[ValidationResult]


class ReconciliationValidator(BaseValidator):
    """Reconciles warehouse source counts against graph node/relationship counts."""

    def __init__(
        self,
        run_id: str,
        neo4j_client: Neo4jClient,
        checkpoint_repo: CheckpointRepository,
        job_run_repo: JobRunRepository,
    ) -> None:
        super().__init__(run_id)
        self._client = neo4j_client
        self._checkpoints = checkpoint_repo
        self._job_runs = job_run_repo

    def validate(self, *args: Any, **kwargs: Any) -> list[ValidationResult]:
        raise NotImplementedError(
            "Use reconcile_source() or reconcile_batch() directly."
        )

    # ── core reconciliation ────────────────────────────────────────────────────

    def reconcile_source(
        self,
        source_name: str,
        warehouse_count: int,
        target_label_or_rel: str,
        expected_skip_count: int = 0,
        threshold_pct: float = 0.05,
    ) -> ReconciliationReport:
        """
        Compare warehouse row count against graph node/rel count for this source.
        Queries the graph for nodes or relationships sourced from source_name.
        """
        results: list[ValidationResult] = []
        graph_node_count: int | None = None
        graph_rel_count: int | None = None

        # Try as a node label first, then as a relationship type.
        try:
            node_query = (
                f"MATCH (n:{target_label_or_rel} {{source_name: $source_name}}) "
                "RETURN count(n) AS cnt"
            )
            records = self._client.query_many(node_query, {"source_name": source_name})
            graph_node_count = records[0]["cnt"] if records else 0
        except Exception:
            pass

        if graph_node_count is None:
            try:
                rel_query = (
                    f"MATCH ()-[r:{target_label_or_rel} {{source_name: $source_name}}]->() "
                    "RETURN count(r) AS cnt"
                )
                records = self._client.query_many(rel_query, {"source_name": source_name})
                graph_rel_count = records[0]["cnt"] if records else 0
            except Exception:
                pass

        graph_count = graph_node_count if graph_node_count is not None else (graph_rel_count or 0)
        effective_load = warehouse_count - expected_skip_count

        check_result = assert_count_within_threshold(
            actual=graph_count,
            expected=max(effective_load, 0),
            threshold_pct=threshold_pct,
            check_name="reconcile_source",
            source=source_name,
            run_id=self._run_id,
        )
        results.append(check_result)

        drift_pct = (
            abs(graph_count - effective_load) / effective_load
            if effective_load > 0
            else (0.0 if graph_count == 0 else 1.0)
        )

        return ReconciliationReport(
            source_name=source_name,
            run_id=self._run_id,
            warehouse_row_count=warehouse_count,
            graph_node_count=graph_node_count,
            graph_rel_count=graph_rel_count,
            expected_skip_count=expected_skip_count,
            effective_load_count=effective_load,
            drift_pct=round(drift_pct, 4),
            within_threshold=check_result.passed,
            results=results,
        )

    def reconcile_batch(
        self,
        batch: GraphWriteBatch,
        warehouse_row_count: int,
        skip_count: int = 0,
        threshold_pct: float = 0.05,
    ) -> ReconciliationReport:
        """
        Reconcile a single batch: compare record counts against warehouse_row_count - skip_count.
        """
        results: list[ValidationResult] = []
        batch_record_count = batch.total_record_count()
        effective_load = max(warehouse_row_count - skip_count, 0)

        check_result = assert_count_within_threshold(
            actual=batch_record_count,
            expected=effective_load,
            threshold_pct=threshold_pct,
            check_name="reconcile_batch",
            source=batch.source_name,
            run_id=self._run_id,
        )
        results.append(check_result)

        drift_pct = (
            abs(batch_record_count - effective_load) / effective_load
            if effective_load > 0
            else (0.0 if batch_record_count == 0 else 1.0)
        )

        node_count: int | None = batch.node_count() or None
        rel_count: int | None = batch.relationship_count() or None

        return ReconciliationReport(
            source_name=batch.source_name,
            run_id=self._run_id,
            warehouse_row_count=warehouse_row_count,
            graph_node_count=node_count,
            graph_rel_count=rel_count,
            expected_skip_count=skip_count,
            effective_load_count=effective_load,
            drift_pct=round(drift_pct, 4),
            within_threshold=check_result.passed,
            results=results,
        )

    # ── checkpoint / run metadata checks ──────────────────────────────────────

    def check_watermark_advanced(
        self, source_name: str, run_id: str,
    ) -> ValidationResult:
        """WARNING if the watermark for this source was not advanced after a successful run."""
        name = "check_watermark_advanced"
        try:
            checkpoint = self._checkpoints.get_checkpoint(
                pipeline_name=run_id, source_name=source_name,
            )
        except Exception as exc:
            return self._fail(name, source_name, ValidationSeverity.ERROR,
                              f"Failed to read checkpoint: {exc}",
                              source_name=source_name)

        if checkpoint is None:
            return self._warn(name, source_name,
                              "No checkpoint record found for this source",
                              source_name=source_name)

        if checkpoint.last_successful_run_id == run_id:
            return self._pass(name, source_name,
                              "Watermark was advanced for this run",
                              run_id=run_id)
        return self._warn(name, source_name,
                          "Watermark was not advanced — checkpoint run_id does not match",
                          source_name=source_name,
                          checkpoint_run_id=checkpoint.last_successful_run_id,
                          expected_run_id=run_id)

    def check_no_duplicate_run_ids(
        self, source_name: str, run_id: str,
    ) -> ValidationResult:
        """ERROR if the same (source_name, run_id) appears multiple times in job_runs."""
        name = "check_no_duplicate_run_ids"
        try:
            runs = self._job_runs.list_runs_by_run_id(run_id)
        except Exception as exc:
            return self._fail(name, source_name, ValidationSeverity.ERROR,
                              f"Failed to query job_runs for duplicates: {exc}",
                              run_id=run_id)

        count = len([r for r in runs if r.run_id == run_id])
        if count <= 1:
            return self._pass(name, source_name,
                              f"run_id '{run_id}' appears exactly once in job_runs")
        return self._fail(name, source_name, ValidationSeverity.ERROR,
                          f"run_id '{run_id}' appears {count} times — duplicated pipeline run",
                          run_id=run_id, occurrence_count=count)

    def check_last_run_succeeded(self, source_name: str) -> ValidationResult:
        """WARNING if the most recent pipeline run for this source did not succeed."""
        name = "check_last_run_succeeded"
        try:
            runs = self._job_runs.list_recent_runs(pipeline_name=source_name, limit=1)
        except Exception as exc:
            return self._fail(name, source_name, ValidationSeverity.ERROR,
                              f"Failed to query recent runs: {exc}",
                              source_name=source_name)

        if not runs:
            return self._warn(name, source_name,
                              "No job run records found for this source",
                              source_name=source_name)

        last = runs[0]
        if last.status == "succeeded":
            return self._pass(name, source_name,
                              "Most recent run succeeded",
                              last_run_id=last.run_id, status=last.status)
        return self._warn(name, source_name,
                          f"Most recent run has status '{last.status}'",
                          source_name=source_name,
                          last_run_id=last.run_id,
                          status=last.status)


def build_reconciliation_summary(
    reports: list[ReconciliationReport],
) -> dict[str, Any]:
    """Return a summary dict with totals, failure counts, and drift stats."""
    total = len(reports)
    failures = [r for r in reports if not r.within_threshold]
    drift_values = [r.drift_pct for r in reports]

    return {
        "total_sources": total,
        "within_threshold": total - len(failures),
        "outside_threshold": len(failures),
        "failed_sources": [r.source_name for r in failures],
        "max_drift_pct": max(drift_values) if drift_values else 0.0,
        "avg_drift_pct": (
            round(sum(drift_values) / len(drift_values), 4) if drift_values else 0.0
        ),
        "total_warehouse_rows": sum(r.warehouse_row_count for r in reports),
        "total_effective_load": sum(r.effective_load_count for r in reports),
    }