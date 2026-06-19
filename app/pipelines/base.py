"""
Pipeline base abstractions.

Every domain pipeline inherits from BasePipeline. PipelineContext is the single
dependency container built once per pipeline run by scripts or the orchestrator.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from time import perf_counter
from typing import Any

from app.canonicalization.base import BaseCanonicalizer
from app.core.constants import (
    CHECKPOINT_STRATEGY_FULL_REFRESH,
    CHECKPOINT_STRATEGY_TIMESTAMP_WATERMARK,
    DEFAULT_CHECKPOINT_NAMESPACE,
)
from app.core.logging import get_logger, log_event
from app.core.time import utc_now
from app.db.checkpoints import CheckpointRepository
from app.db.job_runs import JobRunRepository
from app.db.neo4j_client import Neo4jClient
from app.extractors.base import BaseExtractor
from app.loaders.base import LoadResult
from app.loaders.node_loader import NodeLoader
from app.loaders.relationship_loader import RelationshipLoader
from app.loaders.temporal_loader import TemporalLoader
from app.mappings.source_to_graph import source_emits_graph_records
from app.transformers.base import BaseTransformer
from app.validation.base import ValidationResult, ValidationSeverity
from app.validation.graph_checks import GraphValidator
from app.validation.source_checks import validate_batch
from app.validation.transform_checks import validate_graph_write_batch

LOGGER = get_logger(__name__)

# fct_user_behavior produces PersonaState records and must go through TemporalLoader
_PERSONA_STATE_SOURCE = "fct_user_behavior"


# ── Result types ───────────────────────────────────────────────────────────────

@dataclass
class PipelineResult:
    pipeline_name: str
    run_id: str
    status: str  # completed | failed | partial | dry_run
    sources_processed: list[str] = field(default_factory=list)
    sources_skipped: list[str] = field(default_factory=list)
    sources_failed: list[str] = field(default_factory=list)
    total_rows_extracted: int = 0
    total_nodes_written: int = 0
    total_relationships_written: int = 0
    total_skipped: int = 0
    validation_failures: int = 0
    started_at: str = field(default_factory=lambda: utc_now().isoformat())
    finished_at: str | None = None
    duration_seconds: float | None = None
    error_messages: list[str] = field(default_factory=list)

    def succeeded(self) -> bool:
        return self.status in ("completed", "dry_run")

    def partial(self) -> bool:
        return self.status == "partial"

    def summary(self) -> dict[str, Any]:
        return {
            "pipeline_name": self.pipeline_name,
            "run_id": self.run_id,
            "status": self.status,
            "sources_processed": len(self.sources_processed),
            "sources_skipped": len(self.sources_skipped),
            "sources_failed": len(self.sources_failed),
            "total_rows_extracted": self.total_rows_extracted,
            "total_nodes_written": self.total_nodes_written,
            "total_relationships_written": self.total_relationships_written,
            "total_skipped": self.total_skipped,
            "validation_failures": self.validation_failures,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_seconds": self.duration_seconds,
            "error_messages": self.error_messages,
        }


@dataclass
class SourceRunResult:
    source_name: str
    run_id: str
    status: str  # completed | failed | skipped | non_emitting
    rows_extracted: int = 0
    nodes_written: int = 0
    relationships_written: int = 0
    skip_count: int = 0
    validation_results: list[ValidationResult] = field(default_factory=list)
    load_result: LoadResult | None = None
    error: str | None = None
    duration_seconds: float = 0.0


# ── Dependency container ───────────────────────────────────────────────────────

@dataclass
class PipelineContext:
    """
    Dependency container passed to every pipeline.
    Built once by the orchestrator or script entrypoint.
    """
    run_id: str
    neo4j_client: Neo4jClient
    metadata_db: Any
    checkpoint_repo: CheckpointRepository
    job_runs: JobRunRepository
    extractor_registry: dict[str, BaseExtractor]
    # transformer classes rather than instances; instantiated per-source with run_id
    transformer_registry: dict[str, type[BaseTransformer]]
    canonicalizer_registry: dict[str, BaseCanonicalizer]
    node_loader: NodeLoader
    relationship_loader: RelationshipLoader
    temporal_loader: TemporalLoader
    dry_run: bool = False


def build_pipeline_context(run_id: str, dry_run: bool = False) -> PipelineContext:
    """
    Build a fully-wired PipelineContext from config and registries.
    Called once per pipeline run by scripts or the orchestrator.
    """
    from app.core.config import get_settings
    from app.db.metadata_db import MetadataDBClient
    from app.db.mysql_client import MySQLClient
    from app.loaders.node_loader import build_merge_query_registry

    settings = get_settings()

    mysql_client = MySQLClient(settings)
    neo4j_client = Neo4jClient(settings)
    metadata_db = MetadataDBClient(settings)

    checkpoint_repo = CheckpointRepository(metadata_db)
    job_runs = JobRunRepository(metadata_db)

    merge_query_registry = build_merge_query_registry()
    node_loader = NodeLoader(
        neo4j_client=neo4j_client,
        run_id=run_id,
        merge_query_registry=merge_query_registry,
        dry_run=dry_run,
    )
    relationship_loader = RelationshipLoader(
        neo4j_client=neo4j_client,
        run_id=run_id,
        merge_query_registry=merge_query_registry,
        dry_run=dry_run,
    )
    temporal_loader = TemporalLoader(
        neo4j_client=neo4j_client,
        run_id=run_id,
        merge_query_registry=merge_query_registry,
        dry_run=dry_run,
    )

    extractor_registry = _build_extractor_registry(mysql_client)
    transformer_registry = _build_transformer_registry()
    canonicalizer_registry: dict[str, BaseCanonicalizer] = {}

    return PipelineContext(
        run_id=run_id,
        neo4j_client=neo4j_client,
        metadata_db=metadata_db,
        checkpoint_repo=checkpoint_repo,
        job_runs=job_runs,
        extractor_registry=extractor_registry,
        transformer_registry=transformer_registry,
        canonicalizer_registry=canonicalizer_registry,
        node_loader=node_loader,
        relationship_loader=relationship_loader,
        temporal_loader=temporal_loader,
        dry_run=dry_run,
    )


def _build_extractor_registry(mysql_client: Any) -> dict[str, BaseExtractor]:
    """Import all extractor modules and build a source_name → instance registry."""
    from importlib import import_module
    from pathlib import Path

    registry: dict[str, BaseExtractor] = {}
    pkg_path = Path(__file__).parent.parent / "extractors"

    for py_file in sorted(pkg_path.glob("*.py")):
        if py_file.stem in ("base", "__init__"):
            continue
        try:
            module = import_module(f"app.extractors.{py_file.stem}")
        except Exception as exc:
            log_event(LOGGER, "extractor_registry_import_error",
                      module=py_file.stem, error=str(exc))
            continue
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if (
                isinstance(attr, type)
                and issubclass(attr, BaseExtractor)
                and attr is not BaseExtractor
                and getattr(attr, "source_name", "")
            ):
                try:
                    instance = attr(mysql_client)
                    registry[attr.source_name] = instance
                except Exception as exc:
                    log_event(LOGGER, "extractor_registry_instantiation_error",
                              extractor=attr_name, error=str(exc))

    return registry


def _build_transformer_registry() -> dict[str, type[BaseTransformer]]:
    """Import all transformer modules and build a source_name → class registry."""
    from importlib import import_module
    from pathlib import Path

    registry: dict[str, type[BaseTransformer]] = {}
    pkg_path = Path(__file__).parent.parent / "transformers"

    for py_file in sorted(pkg_path.glob("*.py")):
        if py_file.stem in ("base", "__init__"):
            continue
        try:
            module = import_module(f"app.transformers.{py_file.stem}")
        except Exception as exc:
            log_event(LOGGER, "transformer_registry_import_error",
                      module=py_file.stem, error=str(exc))
            continue
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if (
                isinstance(attr, type)
                and issubclass(attr, BaseTransformer)
                and attr is not BaseTransformer
                and getattr(attr, "source_name", "")
            ):
                registry[attr.source_name] = attr

    return registry


# ── Base pipeline ──────────────────────────────────────────────────────────────

class BasePipeline(ABC):
    """
    Abstract base for all domain pipelines.

    Subclasses declare:
        pipeline_name: str    — must match a PIPELINE_NAMES constant
        sources: tuple[str, ...] — ordered source names to process

    The run() default implementation iterates sources in order and calls
    _run_source() for each. Pipelines with bespoke logic (temporal_pipeline,
    serving_materialization_pipeline) override run() directly.
    """

    pipeline_name: str
    sources: tuple[str, ...] = ()

    def __init__(
        self,
        run_id: str,
        neo4j_client: Neo4jClient,
        metadata_db: Any,
        checkpoint_repo: CheckpointRepository,
        job_runs: JobRunRepository,
        extractor_registry: dict[str, BaseExtractor],
        transformer_registry: dict[str, type[BaseTransformer]],
        node_loader: NodeLoader,
        relationship_loader: RelationshipLoader,
        temporal_loader: TemporalLoader,
        canonicalizer_registry: dict[str, BaseCanonicalizer],
        dry_run: bool = False,
        source_filter: list[str] | None = None,
    ) -> None:
        self._run_id = run_id
        self._neo4j_client = neo4j_client
        self._metadata_db = metadata_db
        self._checkpoint_repo = checkpoint_repo
        self._job_runs = job_runs
        self._extractor_registry = extractor_registry
        self._transformer_registry = transformer_registry
        self._node_loader = node_loader
        self._relationship_loader = relationship_loader
        self._temporal_loader = temporal_loader
        self._canonicalizer_registry = canonicalizer_registry
        self._dry_run = dry_run
        self._source_filter = source_filter
        self._logger = get_logger(__name__, pipeline_name=self.pipeline_name)
        self._graph_validator = GraphValidator(run_id, neo4j_client)

    def run(self) -> PipelineResult:
        """
        Default domain pipeline run — processes self.sources in order.
        Temporal and serving pipelines override this method.
        """
        started = perf_counter()
        started_at = utc_now().isoformat()
        result = PipelineResult(
            pipeline_name=self.pipeline_name,
            run_id=self._run_id,
            status="failed",
            started_at=started_at,
        )

        self._log_pipeline_started()

        try:
            for source_name in self.sources:
                if not self._should_run_source(source_name):
                    result.sources_skipped.append(source_name)
                    continue

                mode = self._get_watermark_mode(source_name)
                source_result = self._run_source(source_name, mode)

                result.total_rows_extracted += source_result.rows_extracted
                result.total_nodes_written += source_result.nodes_written
                result.total_relationships_written += source_result.relationships_written
                result.total_skipped += source_result.skip_count
                result.validation_failures += sum(
                    1 for r in source_result.validation_results if not r.passed
                )

                if source_result.status in ("completed", "non_emitting"):
                    result.sources_processed.append(source_name)
                else:
                    result.sources_failed.append(source_name)
                    if source_result.error:
                        result.error_messages.append(
                            f"{source_name}: {source_result.error}"
                        )

            if self._dry_run:
                result.status = "dry_run"
            elif result.sources_failed:
                result.status = (
                    "partial"
                    if result.sources_processed or [
                        s for s in result.sources_processed
                        if s not in result.sources_failed
                    ]
                    else "failed"
                )
            else:
                result.status = "completed"

        except Exception as exc:
            result.status = "failed"
            result.error_messages.append(str(exc))
            log_event(self._logger, "pipeline_error",
                      pipeline_name=self.pipeline_name,
                      run_id=self._run_id,
                      error=str(exc))

        finally:
            result.finished_at = utc_now().isoformat()
            result.duration_seconds = perf_counter() - started
            self._log_pipeline_finished(result)

        return result

    # ── Source cycle ───────────────────────────────────────────────────────────

    def _run_source(
        self,
        source_name: str,
        mode: str = "incremental",
    ) -> SourceRunResult:
        """
        Full extract → validate → transform → validate → load → checkpoint
        cycle for a single source. All exceptions are caught and returned as
        a failed SourceRunResult so other sources in the pipeline continue.
        """
        started = perf_counter()

        # Step 1 — non-emitting fast-path
        if not source_emits_graph_records(source_name):
            log_event(self._logger, "source_non_emitting",
                      source_name=source_name, run_id=self._run_id)
            return SourceRunResult(
                source_name=source_name,
                run_id=self._run_id,
                status="non_emitting",
                duration_seconds=perf_counter() - started,
            )

        # Step 2 — registry lookup
        extractor = self._extractor_registry.get(source_name)
        transformer_cls = self._transformer_registry.get(source_name)

        if extractor is None:
            return self._failed_result(
                source_name, started,
                f"No extractor registered for source '{source_name}'",
            )
        if transformer_cls is None:
            return self._failed_result(
                source_name, started,
                f"No transformer registered for source '{source_name}'",
            )

        # Step 3 — watermark
        watermark: str | None = None
        if mode == "incremental" and extractor.supports_incremental:
            cp = self._checkpoint_repo.get_checkpoint(
                pipeline_name=self.pipeline_name,
                source_name=source_name,
            )
            watermark = cp.watermark_value if cp else None

        try:
            # Step 4 — extract
            batch = extractor.extract_all(self._run_id, watermark)

            # Step 5 — pre-transform validation
            source_validation = validate_batch(batch, self._run_id)
            if self._has_critical(source_validation):
                critical_msgs = self._critical_messages(source_validation)
                return SourceRunResult(
                    source_name=source_name,
                    run_id=self._run_id,
                    status="failed",
                    rows_extracted=batch.row_count,
                    validation_results=source_validation,
                    error=f"CRITICAL pre-transform: {critical_msgs}",
                    duration_seconds=perf_counter() - started,
                )

            # Step 6 — transform
            transformer = transformer_cls(
                run_id=self._run_id,
                canonicalizer_registry=self._canonicalizer_registry,
            )
            write_batch = transformer.transform(batch)

            # Step 7 — post-transform validation
            transform_validation = validate_graph_write_batch(
                write_batch,
                self._run_id,
                total_input_rows=batch.row_count,
                skip_count=transformer.skip_count,
            )
            all_validation = source_validation + transform_validation
            if self._has_critical(transform_validation):
                critical_msgs = self._critical_messages(transform_validation)
                return SourceRunResult(
                    source_name=source_name,
                    run_id=self._run_id,
                    status="failed",
                    rows_extracted=batch.row_count,
                    skip_count=transformer.skip_count,
                    validation_results=all_validation,
                    error=f"CRITICAL post-transform: {critical_msgs}",
                    duration_seconds=perf_counter() - started,
                )

            # Step 8 — dry-run exit
            if self._dry_run:
                return SourceRunResult(
                    source_name=source_name,
                    run_id=self._run_id,
                    status="completed",
                    rows_extracted=batch.row_count,
                    skip_count=transformer.skip_count,
                    validation_results=all_validation,
                    duration_seconds=perf_counter() - started,
                )

            # Step 8 — load
            load_result = self._load_batch(source_name, write_batch)

            # Step 9 — post-load checks (non-blocking warnings)
            try:
                post_load = self._graph_validator.run_post_load_checks(
                    source_name, write_batch
                )
                all_validation = all_validation + post_load
            except Exception as exc:
                log_event(self._logger, "post_load_check_error",
                          source_name=source_name, error=str(exc))

            # Step 10 — advance checkpoint only on success
            if load_result.succeeded():
                self._advance_checkpoint(source_name, batch.watermark_value, extractor)

            status = "completed" if load_result.succeeded() else "failed"
            return SourceRunResult(
                source_name=source_name,
                run_id=self._run_id,
                status=status,
                rows_extracted=batch.row_count,
                nodes_written=load_result.nodes_written,
                relationships_written=load_result.relationships_written,
                skip_count=transformer.skip_count,
                validation_results=all_validation,
                load_result=load_result,
                error=("; ".join(load_result.errors) if load_result.errors else None),
                duration_seconds=perf_counter() - started,
            )

        except Exception as exc:
            log_event(self._logger, "source_run_error",
                      source_name=source_name, run_id=self._run_id, error=str(exc))
            return SourceRunResult(
                source_name=source_name,
                run_id=self._run_id,
                status="failed",
                error=str(exc),
                duration_seconds=perf_counter() - started,
            )

    def _load_batch(self, source_name: str, write_batch: Any) -> LoadResult:
        """Route load to TemporalLoader for PersonaState, else NodeLoader + RelationshipLoader."""
        if source_name == _PERSONA_STATE_SOURCE:
            return self._temporal_loader.load_persona_states(write_batch)

        node_result = self._node_loader.load(write_batch)
        rel_result = self._relationship_loader.load(write_batch)

        return LoadResult(
            source_name=source_name,
            run_id=self._run_id,
            nodes_written=node_result.nodes_written,
            nodes_skipped=node_result.nodes_skipped,
            relationships_written=rel_result.relationships_written,
            relationships_skipped=rel_result.relationships_skipped,
            errors=node_result.errors + rel_result.errors,
            duration_seconds=node_result.duration_seconds + rel_result.duration_seconds,
            batch_count=node_result.batch_count + rel_result.batch_count,
        )

    def _advance_checkpoint(
        self,
        source_name: str,
        watermark_value: str | None,
        extractor: BaseExtractor,
    ) -> None:
        """Upsert checkpoint after a successful source load."""
        strategy = (
            CHECKPOINT_STRATEGY_TIMESTAMP_WATERMARK
            if extractor.freshness_field
            else CHECKPOINT_STRATEGY_FULL_REFRESH
        )
        try:
            self._checkpoint_repo.upsert_checkpoint(
                namespace=DEFAULT_CHECKPOINT_NAMESPACE,
                pipeline_name=self.pipeline_name,
                source_name=source_name,
                checkpoint_strategy=strategy,
                watermark_value=watermark_value,
                last_successful_run_id=self._run_id,
            )
        except Exception as exc:
            log_event(self._logger, "checkpoint_advance_error",
                      source_name=source_name, error=str(exc))

    # ── Filter / mode helpers ──────────────────────────────────────────────────

    def _should_run_source(self, source_name: str) -> bool:
        """Return True if source is in source_filter (or filter is None)."""
        if self._source_filter is None:
            return True
        return source_name in self._source_filter

    def _get_watermark_mode(self, source_name: str) -> str:
        """Return 'full_refresh' for non-incremental sources, else 'incremental'."""
        extractor = self._extractor_registry.get(source_name)
        if extractor is None or not extractor.supports_incremental:
            return "full_refresh"
        return "incremental"

    # ── Validation helpers ─────────────────────────────────────────────────────

    @staticmethod
    def _has_critical(results: list[ValidationResult]) -> bool:
        return any(
            not r.passed and r.severity == ValidationSeverity.CRITICAL
            for r in results
        )

    @staticmethod
    def _critical_messages(results: list[ValidationResult]) -> str:
        return "; ".join(
            r.message for r in results
            if not r.passed and r.severity == ValidationSeverity.CRITICAL
        )

    # ── Logging helpers ────────────────────────────────────────────────────────

    def _log_pipeline_started(self) -> None:
        log_event(
            self._logger,
            "pipeline_started",
            pipeline_name=self.pipeline_name,
            run_id=self._run_id,
            dry_run=self._dry_run,
            source_count=len(self.sources),
        )

    def _log_pipeline_finished(self, result: PipelineResult) -> None:
        log_event(
            self._logger,
            "pipeline_finished",
            pipeline_name=self.pipeline_name,
            run_id=self._run_id,
            status=result.status,
            sources_processed=len(result.sources_processed),
            sources_failed=len(result.sources_failed),
            total_nodes_written=result.total_nodes_written,
            total_relationships_written=result.total_relationships_written,
            duration_seconds=result.duration_seconds,
        )

    @staticmethod
    def _failed_result(
        source_name: str,
        started: float,
        error: str,
    ) -> SourceRunResult:
        return SourceRunResult(
            source_name=source_name,
            run_id="",
            status="failed",
            error=error,
            duration_seconds=perf_counter() - started,
        )
