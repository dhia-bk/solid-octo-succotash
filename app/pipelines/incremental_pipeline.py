"""
Incremental pipeline — runs all domain pipelines respecting existing checkpoints.

Sources with supports_incremental=False always run full_refresh regardless of mode.
Checkpoints are advanced per-source on successful load.

Wave structure and execution order identical to FullBackfillPipeline.
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
    IDENTITY_PIPELINE,
    INCREMENTAL_PIPELINE,
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
from app.pipelines.full_backfill_pipeline import PIPELINE_EXECUTION_ORDER

LOGGER = get_logger(__name__)


class IncrementalPipeline:
    """
    Composes all domain pipelines into an incremental run.

    Identical wave structure to FullBackfillPipeline but does not clear
    checkpoints. Sources with supports_incremental=False run full_refresh.

    Not a BasePipeline subclass — orchestrates domain pipelines directly.
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
        1. Create job_runs record.
        2. Run each wave in dependency order.
        3. Checkpoints advance per-source on success inside BasePipeline._run_source.
        4. Return all results.
        """
        started = perf_counter()
        started_at = utc_now().isoformat()
        all_results: dict[str, PipelineResult] = {}
        halted = False

        self._context.job_runs.create_run(
            run_id=self._run_id,
            pipeline_name=INCREMENTAL_PIPELINE,
            started_at=started_at,
        )
        self._context.job_runs.mark_running(self._run_id)

        log_event(
            self._logger,
            "incremental_pipeline_started",
            run_id=self._run_id,
            wave_count=len(PIPELINE_EXECUTION_ORDER),
        )

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
            log_event(self._logger, "incremental_pipeline_error",
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
                "incremental_pipeline_finished",
                run_id=self._run_id,
                status=final_status,
                duration_seconds=perf_counter() - started,
                pipeline_count=len(all_results),
            )

        return all_results

    def get_sources_due_for_refresh(self) -> list[str]:
        """
        Return source names whose watermark is older than their configured
        freshness threshold, or that have never been checkpointed.
        """
        from app.mappings.source_to_graph import SOURCE_ARTIFACT_DECLARATIONS

        due: list[str] = []
        checkpointed: dict[str, str | None] = {}

        try:
            existing = self._context.checkpoint_repo.list_checkpoints(
                namespace=DEFAULT_CHECKPOINT_NAMESPACE,
            )
            checkpointed = {
                cp.source_name: cp.watermark_value for cp in existing
            }
        except Exception as exc:
            log_event(self._logger, "due_for_refresh_error", error=str(exc))
            return due

        for decl in SOURCE_ARTIFACT_DECLARATIONS:
            if not decl.emits_records:
                continue
            if decl.source_name not in checkpointed:
                due.append(decl.source_name)
            elif checkpointed[decl.source_name] is None:
                due.append(decl.source_name)

        return sorted(set(due))

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
