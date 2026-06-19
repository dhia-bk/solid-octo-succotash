"""
Analytics loader — writes GDS algorithm outputs back to graph nodes.

Used after analytics jobs complete (Leiden, PageRank, inference) to persist
results as node properties and create audit trail nodes.
"""

from __future__ import annotations

from time import perf_counter
from typing import Any

from app.contracts.graph_records import GraphWriteBatch
from app.core.constants import PERSONA_STATE, USER
from app.core.logging import get_logger, log_event
from app.db.neo4j_client import Neo4jClient
from app.loaders.base import BaseLoader, LoadResult

# ── Analytics write queries ──────────────────────────────────────────────────

_WRITE_TRIBE_ASSIGNMENTS_QUERY = """\
UNWIND $rows AS row
MATCH (u:User {id: row.user_id})
SET u.tribe_id = row.tribe_id,
    u._run_id  = row.run_id,
    u._updated_at = row.updated_at"""

_WRITE_PAGERANK_SCORES_QUERY = """\
UNWIND $rows AS row
MATCH (u:User {id: row.user_id})
SET u.pagerank_score = row.pagerank_score,
    u._run_id        = row.run_id,
    u._updated_at    = row.updated_at"""

_WRITE_INFERENCE_RESULTS_QUERY = """\
UNWIND $rows AS row
MATCH (u:User {id: row.user_id})
SET u.inferred_topic  = row.inferred_topic,
    u.inferred_confidence = row.confidence,
    u._run_id         = row.run_id,
    u._updated_at     = row.updated_at"""

_MERGE_PIPELINE_RUN_NODE_QUERY = """\
MERGE (pr:PipelineRun {id: $run_id})
ON CREATE SET
    pr.source_name  = $source_name,
    pr.node_count   = $node_count,
    pr.rel_count    = $rel_count,
    pr.started_at   = $started_at,
    pr.finished_at  = $finished_at,
    pr._created_at  = $finished_at
ON MATCH SET
    pr.node_count   = $node_count,
    pr.rel_count    = $rel_count,
    pr.finished_at  = $finished_at,
    pr._updated_at  = $finished_at"""


class AnalyticsLoader(BaseLoader):
    """
    Writes GDS algorithm outputs (tribe_id, pagerank_score, etc.) back
    to graph nodes after analytics jobs complete.

    Also creates PipelineRun audit trail nodes.
    """

    def load(self, batch: GraphWriteBatch) -> LoadResult:
        """Not used directly; analytics loader uses domain-specific methods."""
        raise NotImplementedError(
            "AnalyticsLoader does not implement generic load(). "
            "Use write_tribe_assignments(), write_pagerank_scores(), "
            "write_inference_results(), or write_pipeline_run_node()."
        )

    def write_tribe_assignments(
        self,
        assignments: list[dict[str, Any]],
    ) -> LoadResult:
        """
        Bulk-write tribe_id property to User nodes.

        Args:
            assignments: List of {user_id, tribe_id, run_id} dicts.
        """
        started = perf_counter()
        result = LoadResult(source_name="leiden_analytics", run_id=self._run_id)

        log_event(
            self._logger,
            event_name="tribe_assignment_write_started",
            message="Writing tribe assignments to User nodes",
            run_id=self._run_id,
            record_count=len(assignments),
        )

        from app.core.time import format_iso_timestamp, utc_now
        now = format_iso_timestamp(utc_now())
        rows = [
            {
                "user_id": str(a["user_id"]),
                "tribe_id": a["tribe_id"],
                "run_id": a.get("run_id", self._run_id),
                "updated_at": now,
            }
            for a in assignments
            if a.get("user_id") is not None
        ]

        if not self._dry_run and rows:
            self._execute_batch(_WRITE_TRIBE_ASSIGNMENTS_QUERY, rows)

        result.nodes_written = len(rows)
        result.batch_count = 1
        result.duration_seconds = self._elapsed(started)

        log_event(
            self._logger,
            event_name="tribe_assignment_write_finished",
            message="Tribe assignment write complete",
            run_id=self._run_id,
            written=result.nodes_written,
        )
        return result

    def write_pagerank_scores(
        self,
        scores: list[dict[str, Any]],
    ) -> LoadResult:
        """
        Bulk-write pagerank_score property to User nodes.

        Args:
            scores: List of {user_id, pagerank_score, run_id} dicts.
        """
        started = perf_counter()
        result = LoadResult(source_name="pagerank_analytics", run_id=self._run_id)

        log_event(
            self._logger,
            event_name="pagerank_write_started",
            message="Writing PageRank scores to User nodes",
            run_id=self._run_id,
            record_count=len(scores),
        )

        from app.core.time import format_iso_timestamp, utc_now
        now = format_iso_timestamp(utc_now())
        rows = [
            {
                "user_id": str(s["user_id"]),
                "pagerank_score": float(s["pagerank_score"]),
                "run_id": s.get("run_id", self._run_id),
                "updated_at": now,
            }
            for s in scores
            if s.get("user_id") is not None
        ]

        if not self._dry_run and rows:
            self._execute_batch(_WRITE_PAGERANK_SCORES_QUERY, rows)

        result.nodes_written = len(rows)
        result.batch_count = 1
        result.duration_seconds = self._elapsed(started)

        log_event(
            self._logger,
            event_name="pagerank_write_finished",
            message="PageRank write complete",
            run_id=self._run_id,
            written=result.nodes_written,
        )
        return result

    def write_inference_results(
        self,
        results_in: list[dict[str, Any]],
    ) -> LoadResult:
        """
        Write inference outputs to User nodes.

        Args:
            results_in: List of {user_id, inferred_topic, confidence, run_id} dicts.
        """
        started = perf_counter()
        result = LoadResult(source_name="inference_analytics", run_id=self._run_id)

        from app.core.time import format_iso_timestamp, utc_now
        now = format_iso_timestamp(utc_now())
        rows = [
            {
                "user_id": str(r["user_id"]),
                "inferred_topic": r["inferred_topic"],
                "confidence": float(r.get("confidence", 0.0)),
                "run_id": r.get("run_id", self._run_id),
                "updated_at": now,
            }
            for r in results_in
            if r.get("user_id") is not None
        ]

        if not self._dry_run and rows:
            self._execute_batch(_WRITE_INFERENCE_RESULTS_QUERY, rows)

        result.nodes_written = len(rows)
        result.batch_count = 1
        result.duration_seconds = self._elapsed(started)
        return result

    def write_pipeline_run_node(
        self,
        run_id: str,
        source_name: str,
        node_count: int,
        rel_count: int,
        started_at: str,
        finished_at: str,
    ) -> None:
        """
        MERGE a PipelineRun node in the graph for audit trail.
        """
        if self._dry_run:
            log_event(
                self._logger,
                event_name="pipeline_run_node_dry_run",
                message="Dry-run: skipped PipelineRun node write",
                run_id=run_id,
            )
            return

        self._execute(
            _MERGE_PIPELINE_RUN_NODE_QUERY,
            {
                "run_id": run_id,
                "source_name": source_name,
                "node_count": node_count,
                "rel_count": rel_count,
                "started_at": started_at,
                "finished_at": finished_at,
            },
        )

        log_event(
            self._logger,
            event_name="pipeline_run_node_written",
            message="PipelineRun audit node written",
            run_id=run_id,
            source_name=source_name,
            node_count=node_count,
            rel_count=rel_count,
        )
