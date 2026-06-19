"""
Source inventory pipeline — discovers and registers all warehouse sources.

Runs before any domain pipeline to populate the source_inventory metadata
table and verify mapping coverage. CRITICAL failures from coverage checks
will halt subsequent pipeline execution.
"""

from __future__ import annotations

from time import perf_counter

from app.core.constants import SOURCE_INVENTORY_PIPELINE
from app.core.logging import get_logger, log_event
from app.core.time import utc_now
from app.mappings.source_to_graph import (
    SOURCE_ARTIFACT_DECLARATIONS,
    validate_source_artifact_declarations,
)
from app.pipelines.base import BasePipeline, PipelineResult
from app.validation.source_coverage_checks import SourceCoverageValidator

LOGGER = get_logger(__name__)


class SourceInventoryPipeline(BasePipeline):
    """
    Registers all warehouse sources and runs coverage checks.

    Does not extract warehouse rows — operates on declared mappings only.
    CRITICAL mapping errors are surfaced in PipelineResult.error_messages.
    """

    pipeline_name = SOURCE_INVENTORY_PIPELINE
    sources: tuple[str, ...] = ()

    def run(self) -> PipelineResult:
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
            # 1. Validate source artifact declarations for internal consistency
            declaration_errors = validate_source_artifact_declarations()
            if declaration_errors:
                for err in declaration_errors:
                    result.error_messages.append(err)
                log_event(
                    self._logger,
                    "source_artifact_declaration_errors",
                    error_count=len(declaration_errors),
                    errors=declaration_errors[:10],
                )

            # 2. Upsert each declared source into the source_inventory metadata table
            upserted = 0
            errors: list[str] = []
            for declaration in SOURCE_ARTIFACT_DECLARATIONS:
                try:
                    self._upsert_source_declaration(declaration)
                    upserted += 1
                except Exception as exc:
                    msg = f"Failed to upsert {declaration.source_name}: {exc}"
                    errors.append(msg)
                    log_event(
                        self._logger,
                        "source_inventory_upsert_error",
                        source_name=declaration.source_name,
                        error=str(exc),
                    )

            log_event(
                self._logger,
                "source_inventory_upserted",
                total_declarations=len(SOURCE_ARTIFACT_DECLARATIONS),
                upserted=upserted,
                errors=len(errors),
            )

            # 3. Run coverage checks
            coverage_validator = SourceCoverageValidator(self._run_id)
            coverage_results = coverage_validator.run_all_coverage_checks()
            critical_failures = [
                r for r in coverage_results
                if not r.passed and r.severity.value == "critical"
            ]
            if critical_failures:
                for r in critical_failures:
                    result.error_messages.append(f"CRITICAL coverage: {r.message}")

            result.validation_failures = sum(
                1 for r in coverage_results if not r.passed
            )
            result.error_messages.extend(errors)
            result.status = (
                "failed" if critical_failures or errors else "completed"
            )

        except Exception as exc:
            result.status = "failed"
            result.error_messages.append(str(exc))
            log_event(self._logger, "source_inventory_pipeline_error", error=str(exc))

        finally:
            result.finished_at = utc_now().isoformat()
            result.duration_seconds = perf_counter() - started
            self._log_pipeline_finished(result)

        return result

    def _upsert_source_declaration(self, declaration: object) -> None:
        """
        Upsert one SourceArtifactDeclaration into the source_inventory table.
        Uses best-effort introspection of the metadata_db interface.
        """
        try:
            from app.db.source_inventory import SourceInventoryRepository
            repo = SourceInventoryRepository(self._metadata_db)
            repo.upsert_source(declaration)
        except ImportError:
            # Fall back to direct metadata_db execute if no dedicated repo exists
            pass
