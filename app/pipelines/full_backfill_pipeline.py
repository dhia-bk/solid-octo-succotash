"""
Full backfill pipeline — runs all domain pipelines from scratch.

Clears all checkpoints before execution so every extractor performs a
full table scan regardless of prior incremental state.

Wave structure mirrors PipelineDependencyGraph execution order:
- Wave 0: infrastructure (source_inventory, constraints)
- Wave 1: identity anchor
- Wave 2: sports + AI (independent of each other)
- Wave 3: social + content + behavior (all depend on identity)
- Wave 4: intelligence + economy + competition (need identity + sports)
- Wave 5: communication + moderation (need identity)
- Wave 6: analytics features + notifications (non-emitting, no deps)
- Wave 7: temporal (needs behavior + intelligence)

Any CRITICAL failure halts remaining waves.
"""

from __future__ import annotations

import concurrent.futures
from time import perf_counter
from typing import Any

from app.core.constants import (
    AI_PIPELINE,
    ANALYTICS_FEATURE_PIPELINE,
    BEHAVIOR_PIPELINE,
    COMMUNICATION_PIPELINE,
    COMPETITION_PIPELINE,
    CONSTRAINTS_PIPELINE,
    CONTENT_PIPELINE,
    DEFAULT_CHECKPOINT_NAMESPACE,
    ECONOMY_PIPELINE,
    FULL_BACKFILL_PIPELINE,
    IDENTITY_PIPELINE,
    INTELLIGENCE_PIPELINE,
    MODERATION_PIPELINE,
    NOTIFICATIONS_PIPELINE,
    SOCIAL_PIPELINE,
    SOURCE_INVENTORY_PIPELINE,
    SPORTS_PIPELINE,
    TEMPORAL_PIPELINE,
)
from app.core.logging import get_logger, log_event
from app.core.time import utc_now
from app.pipelines.base import PipelineContext, PipelineResult

LOGGER = get_logger(__name__)

PIPELINE_EXECUTION_ORDER: list[list[str]] = [
    # Wave 0 — infrastructure
    [SOURCE_INVENTORY_PIPELINE, CONSTRAINTS_PIPELINE],
    # Wave 1 — identity anchor
    [IDENTITY_PIPELINE],
    # Wave 2 — sports + AI (independent of each other)
    [SPORTS_PIPELINE, AI_PIPELINE],
    # Wave 3 — social + content + behavior (depend on identity)
    [SOCIAL_PIPELINE, CONTENT_PIPELINE, BEHAVIOR_PIPELINE],
    # Wave 4 — intelligence + economy + competition
    [INTELLIGENCE_PIPELINE, ECONOMY_PIPELINE, COMPETITION_PIPELINE],
    # Wave 5 — communication + moderation (depend on identity)
    [COMMUNICATION_PIPELINE, MODERATION_PIPELINE],
    # Wave 6 — analytics features + notifications (non-emitting, no deps)
    [ANALYTICS_FEATURE_PIPELINE, NOTIFICATIONS_PIPELINE],
    # Wave 7 — temporal (depends on behavior + intelligence)
    [TEMPORAL_PIPELINE],
]


class FullBackfillPipeline:
    """
    Composes all domain pipelines into a complete full-refresh run.

    Not a BasePipeline subclass — orchestrates domain pipelines rather than
    processing warehouse sources directly.
    """

    def __init__(
        self,
        context: PipelineContext,
        max_parallel_workers: int = 1,
    ) -> None:
        self._context = context
        self._run_id = context.run_id
        self._max_parallel = max_parallel_workers
        self._logger = get_logger(__name__, run_id=context.run_id)

    def run(self) -> dict[str, PipelineResult]:
        """
        1. Clear all checkpoints (full refresh = start from zero).
        2. Create job_runs record.
        3. Run each wave sequentially; within a wave parallelize if configured.
        4. On any CRITICAL failure: halt remaining waves.
        5. Return all results.
        """
        started = perf_counter()
        started_at = utc_now().isoformat()
        all_results: dict[str, PipelineResult] = {}
        halted = False

        self._context.job_runs.create_run(
            run_id=self._run_id,
            pipeline_name=FULL_BACKFILL_PIPELINE,
            started_at=started_at,
        )
        self._context.job_runs.mark_running(self._run_id)

        log_event(
            self._logger,
            "full_backfill_started",
            run_id=self._run_id,
            wave_count=len(PIPELINE_EXECUTION_ORDER),
        )

        # Clear all checkpoints — full refresh starts from zero
        self._clear_all_checkpoints()

        final_status = "succeeded"

        try:
            for wave_idx, wave in enumerate(PIPELINE_EXECUTION_ORDER):
                if halted:
                    log_event(
                        self._logger,
                        "wave_skipped_halted",
                        wave=wave_idx,
                        pipelines=wave,
                    )
                    continue

                log_event(
                    self._logger, "wave_started",
                    wave=wave_idx, pipelines=wave,
                )

                wave_results = self._run_wave(wave)
                all_results.update(wave_results)

                failed = [n for n, r in wave_results.items() if r.status == "failed"]
                if failed:
                    log_event(
                        self._logger, "wave_critical_failure",
                        wave=wave_idx, failed_pipelines=failed,
                    )
                    halted = True
                    final_status = "failed"

                log_event(
                    self._logger, "wave_finished",
                    wave=wave_idx,
                    statuses={n: r.status for n, r in wave_results.items()},
                )

        except Exception as exc:
            final_status = "failed"
            log_event(self._logger, "full_backfill_error",
                      run_id=self._run_id, error=str(exc))

        finally:
            finished_at = utc_now().isoformat()
            if final_status == "succeeded":
                self._context.job_runs.mark_succeeded(
                    self._run_id, finished_at=finished_at
                )
            else:
                self._context.job_runs.mark_failed(
                    self._run_id, finished_at=finished_at
                )
            log_event(
                self._logger,
                "full_backfill_finished",
                run_id=self._run_id,
                status=final_status,
                duration_seconds=perf_counter() - started,
                pipeline_count=len(all_results),
            )

        return all_results

    def _run_wave(self, pipeline_names: list[str]) -> dict[str, PipelineResult]:
        if self._max_parallel > 1 and len(pipeline_names) > 1:
            return self._run_wave_parallel(pipeline_names)
        return self._run_wave_sequential(pipeline_names)

    def _run_wave_sequential(
        self, pipeline_names: list[str]
    ) -> dict[str, PipelineResult]:
        from app.pipelines.orchestration import PIPELINE_REGISTRY, _register_pipelines
        if not PIPELINE_REGISTRY:
            _register_pipelines()

        results: dict[str, PipelineResult] = {}
        for name in pipeline_names:
            results[name] = self._run_one_pipeline(name)
        return results

    def _run_wave_parallel(
        self, pipeline_names: list[str]
    ) -> dict[str, PipelineResult]:
        from app.pipelines.orchestration import PIPELINE_REGISTRY, _register_pipelines
        if not PIPELINE_REGISTRY:
            _register_pipelines()

        results: dict[str, PipelineResult] = {}
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=self._max_parallel
        ) as executor:
            future_to_name = {
                executor.submit(self._run_one_pipeline, name): name
                for name in pipeline_names
            }
            for future in concurrent.futures.as_completed(future_to_name):
                name = future_to_name[future]
                try:
                    results[name] = future.result()
                except Exception as exc:
                    results[name] = PipelineResult(
                        pipeline_name=name,
                        run_id=self._run_id,
                        status="failed",
                        error_messages=[str(exc)],
                        started_at=utc_now().isoformat(),
                        finished_at=utc_now().isoformat(),
                    )
        return results

    def _run_one_pipeline(self, pipeline_name: str) -> PipelineResult:
        from app.pipelines.orchestration import PIPELINE_REGISTRY
        cls = PIPELINE_REGISTRY[pipeline_name]
        pipeline = cls(
            run_id=self._run_id,
            neo4j_client=self._context.neo4j_client,
            metadata_db=self._context.metadata_db,
            checkpoint_repo=self._context.checkpoint_repo,
            job_runs=self._context.job_runs,
            extractor_registry=self._context.extractor_registry,
            transformer_registry=self._context.transformer_registry,
            node_loader=self._context.node_loader,
            relationship_loader=self._context.relationship_loader,
            temporal_loader=self._context.temporal_loader,
            canonicalizer_registry=self._context.canonicalizer_registry,
            dry_run=self._context.dry_run,
        )
        return pipeline.run()

    def _clear_all_checkpoints(self) -> None:
        """Delete all checkpoints so extractors perform full table scans."""
        try:
            existing = self._context.checkpoint_repo.list_checkpoints(
                namespace=DEFAULT_CHECKPOINT_NAMESPACE,
            )
            for cp in existing:
                self._context.checkpoint_repo.delete_checkpoint(
                    namespace=cp.namespace,
                    pipeline_name=cp.pipeline_name,
                    source_name=cp.source_name,
                )
            log_event(
                self._logger,
                "checkpoints_cleared",
                count=len(existing),
                run_id=self._run_id,
            )
        except Exception as exc:
            log_event(
                self._logger,
                "checkpoint_clear_error",
                error=str(exc),
                run_id=self._run_id,
            )
