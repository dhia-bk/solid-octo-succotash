"""
Pipeline orchestration — dependency graph, execution ordering, and top-level runner.
"""

from __future__ import annotations

import concurrent.futures
from typing import TYPE_CHECKING

from app.core.constants import (
    AI_PIPELINE,
    ANALYTICS_FEATURE_PIPELINE,
    BEHAVIOR_PIPELINE,
    COMMUNICATION_PIPELINE,
    COMPETITION_PIPELINE,
    CONSTRAINTS_PIPELINE,
    CONTENT_PIPELINE,
    ECONOMY_PIPELINE,
    IDENTITY_PIPELINE,
    INTELLIGENCE_PIPELINE,
    MODERATION_PIPELINE,
    NOTIFICATIONS_PIPELINE,
    SERVING_MATERIALIZATION_PIPELINE,
    SOCIAL_PIPELINE,
    SOURCE_INVENTORY_PIPELINE,
    SPORTS_PIPELINE,
    TEMPORAL_PIPELINE,
)
from app.core.exceptions import ConfigurationError
from app.core.logging import get_logger, log_event

if TYPE_CHECKING:
    from app.pipelines.base import BasePipeline, PipelineContext, PipelineResult

LOGGER = get_logger(__name__)


class PipelineDependencyGraph:
    """
    Directed acyclic graph of pipeline dependencies.

    Produces execution waves — pipelines in the same wave have no mutual
    dependencies and may run in parallel.
    """

    DEPENDENCIES: dict[str, list[str]] = {
        SOCIAL_PIPELINE:        [IDENTITY_PIPELINE],
        CONTENT_PIPELINE:       [IDENTITY_PIPELINE],
        BEHAVIOR_PIPELINE:      [IDENTITY_PIPELINE],
        INTELLIGENCE_PIPELINE:  [IDENTITY_PIPELINE, SPORTS_PIPELINE],
        COMPETITION_PIPELINE:   [IDENTITY_PIPELINE, SPORTS_PIPELINE],
        ECONOMY_PIPELINE:       [IDENTITY_PIPELINE],
        COMMUNICATION_PIPELINE: [IDENTITY_PIPELINE],
        AI_PIPELINE:            [IDENTITY_PIPELINE],
        MODERATION_PIPELINE:    [IDENTITY_PIPELINE],
        TEMPORAL_PIPELINE:      [BEHAVIOR_PIPELINE, INTELLIGENCE_PIPELINE],
        SERVING_MATERIALIZATION_PIPELINE: [
            TEMPORAL_PIPELINE,
            COMPETITION_PIPELINE,
            INTELLIGENCE_PIPELINE,
        ],
    }

    def get_execution_order(self, pipelines: list[str]) -> list[list[str]]:
        """
        Return pipelines grouped into dependency-ordered waves.

        Pipelines in the same wave have no dependencies on each other
        and may run in parallel.
        """
        pipeline_set = set(pipelines)
        deps = {
            p: [d for d in self.DEPENDENCIES.get(p, []) if d in pipeline_set]
            for p in pipelines
        }

        waves: list[list[str]] = []
        completed: set[str] = set()
        remaining = set(pipelines)

        while remaining:
            wave = sorted(
                p for p in remaining
                if all(d in completed for d in deps[p])
            )
            if not wave:
                cycle_candidates = sorted(remaining)
                raise ConfigurationError(
                    "Pipeline dependency cycle detected or unresolvable dependency",
                    remaining=cycle_candidates,
                )
            waves.append(wave)
            completed.update(wave)
            remaining -= set(wave)

        return waves

    def validate_no_cycles(self) -> None:
        """Raise ConfigurationError if any dependency cycle is detected."""
        all_pipelines = list(self.DEPENDENCIES.keys()) + [
            p for deps in self.DEPENDENCIES.values() for p in deps
        ]
        all_pipelines = list(set(all_pipelines))
        self.get_execution_order(all_pipelines)


class PipelineOrchestrator:
    """
    Runs multiple pipelines in dependency order.
    Supports sequential and parallel wave execution.
    """

    def __init__(
        self,
        context: PipelineContext,
        max_parallel_workers: int = 1,
    ) -> None:
        self._context = context
        self._max_parallel = max_parallel_workers
        self._dep_graph = PipelineDependencyGraph()
        self._logger = get_logger(__name__, run_id=context.run_id)

    def run_all(
        self,
        pipeline_names: list[str] | None = None,
        mode: str = "incremental",
    ) -> dict[str, PipelineResult]:
        """
        Run all pipelines (or a subset) in dependency order.
        Returns dict of pipeline_name → PipelineResult.
        """
        names = pipeline_names or _DEFAULT_DOMAIN_PIPELINES
        waves = self._dep_graph.get_execution_order(names)

        all_results: dict[str, PipelineResult] = {}
        halted = False

        for wave_idx, wave in enumerate(waves):
            if halted:
                for name in wave:
                    log_event(
                        self._logger, event_name="pipeline_wave_skipped",
                        wave=wave_idx, pipeline_name=name,
                        reason="prior critical failure",
                    )
                continue

            log_event(
                self._logger, event_name="pipeline_wave_started",
                wave=wave_idx, pipelines=wave,
            )

            wave_results = self._run_wave(wave, mode=mode)
            all_results.update(wave_results)

            for name, result in wave_results.items():
                if result.status == "failed":
                    log_event(
                        self._logger, event_name="pipeline_wave_critical_failure",
                        pipeline_name=name, wave=wave_idx,
                    )
                    halted = True

            log_event(
                self._logger, event_name="pipeline_wave_finished",
                wave=wave_idx,
                statuses={n: r.status for n, r in wave_results.items()},
            )

        return all_results

    def run_pipeline(
        self,
        pipeline_name: str,
        mode: str = "incremental",
    ) -> PipelineResult:
        """Run a single named pipeline."""
        pipeline = self._build_pipeline(pipeline_name)
        return pipeline.run()

    def _run_wave(
        self,
        pipeline_names: list[str],
        mode: str,
    ) -> dict[str, PipelineResult]:
        """Run a wave of pipelines; parallel when max_parallel_workers > 1."""
        if self._max_parallel > 1 and len(pipeline_names) > 1:
            return self._run_wave_parallel(pipeline_names)
        return self._run_wave_sequential(pipeline_names)

    def _run_wave_sequential(
        self, pipeline_names: list[str]
    ) -> dict[str, PipelineResult]:
        results: dict[str, PipelineResult] = {}
        for name in pipeline_names:
            results[name] = self.run_pipeline(name)
        return results

    def _run_wave_parallel(
        self, pipeline_names: list[str]
    ) -> dict[str, PipelineResult]:
        results: dict[str, PipelineResult] = {}
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=self._max_parallel
        ) as executor:
            future_to_name = {
                executor.submit(self.run_pipeline, name): name
                for name in pipeline_names
            }
            for future in concurrent.futures.as_completed(future_to_name):
                name = future_to_name[future]
                try:
                    results[name] = future.result()
                except Exception as exc:
                    from app.pipelines.base import PipelineResult
                    from app.core.time import utc_now
                    results[name] = PipelineResult(
                        pipeline_name=name,
                        run_id=self._context.run_id,
                        status="failed",
                        error_messages=[str(exc)],
                        started_at=utc_now().isoformat(),
                        finished_at=utc_now().isoformat(),
                    )
        return results

    def _build_pipeline(self, pipeline_name: str) -> BasePipeline:
        """Instantiate the named pipeline class with the shared context."""
        cls = PIPELINE_REGISTRY.get(pipeline_name)
        if cls is None:
            raise ConfigurationError(
                f"Unknown pipeline '{pipeline_name}'",
                known_pipelines=sorted(PIPELINE_REGISTRY.keys()),
            )
        return cls(
            run_id=self._context.run_id,
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


# Default ordered domain pipeline list (excludes infrastructure pipelines)
_DEFAULT_DOMAIN_PIPELINES: list[str] = [
    SOURCE_INVENTORY_PIPELINE,
    CONSTRAINTS_PIPELINE,
    IDENTITY_PIPELINE,
    SPORTS_PIPELINE,
    AI_PIPELINE,
    SOCIAL_PIPELINE,
    CONTENT_PIPELINE,
    BEHAVIOR_PIPELINE,
    INTELLIGENCE_PIPELINE,
    ECONOMY_PIPELINE,
    COMPETITION_PIPELINE,
    COMMUNICATION_PIPELINE,
    MODERATION_PIPELINE,
    ANALYTICS_FEATURE_PIPELINE,
    NOTIFICATIONS_PIPELINE,
    TEMPORAL_PIPELINE,
]


# Registry populated after all pipeline modules are imported
PIPELINE_REGISTRY: dict[str, type[BasePipeline]] = {}


def _register_pipelines() -> None:
    """Populate PIPELINE_REGISTRY after all modules are imported."""
    from app.pipelines.ai_pipeline import AIPipeline
    from app.pipelines.analytics_feature_pipeline import AnalyticsFeaturePipeline
    from app.pipelines.behavior_pipeline import BehaviorPipeline
    from app.pipelines.communication_pipeline import CommunicationPipeline
    from app.pipelines.competition_pipeline import CompetitionPipeline
    from app.pipelines.constraints_pipeline import ConstraintsPipeline
    from app.pipelines.content_pipeline import ContentPipeline
    from app.pipelines.economy_pipeline import EconomyPipeline
    from app.pipelines.identity_pipeline import IdentityPipeline
    from app.pipelines.intelligence_pipeline import IntelligencePipeline
    from app.pipelines.moderation_pipeline import ModerationPipeline
    from app.pipelines.notifications_pipeline import NotificationsPipeline
    from app.pipelines.serving_materialization_pipeline import ServingMaterializationPipeline
    from app.pipelines.social_pipeline import SocialPipeline
    from app.pipelines.source_inventory_pipeline import SourceInventoryPipeline
    from app.pipelines.sports_pipeline import SportsPipeline
    from app.pipelines.temporal_pipeline import TemporalPipeline

    PIPELINE_REGISTRY.update({
        SOURCE_INVENTORY_PIPELINE:        SourceInventoryPipeline,
        CONSTRAINTS_PIPELINE:             ConstraintsPipeline,
        IDENTITY_PIPELINE:                IdentityPipeline,
        SPORTS_PIPELINE:                  SportsPipeline,
        SOCIAL_PIPELINE:                  SocialPipeline,
        CONTENT_PIPELINE:                 ContentPipeline,
        BEHAVIOR_PIPELINE:                BehaviorPipeline,
        INTELLIGENCE_PIPELINE:            IntelligencePipeline,
        AI_PIPELINE:                      AIPipeline,
        ECONOMY_PIPELINE:                 EconomyPipeline,
        COMPETITION_PIPELINE:             CompetitionPipeline,
        COMMUNICATION_PIPELINE:           CommunicationPipeline,
        NOTIFICATIONS_PIPELINE:           NotificationsPipeline,
        MODERATION_PIPELINE:              ModerationPipeline,
        ANALYTICS_FEATURE_PIPELINE:       AnalyticsFeaturePipeline,
        TEMPORAL_PIPELINE:                TemporalPipeline,
        SERVING_MATERIALIZATION_PIPELINE: ServingMaterializationPipeline,
    })
