"""
Constraints pipeline — verifies Neo4j constraints and indexes before any loads run.

A missing required constraint halts all subsequent pipeline execution with
ConfigurationError. Missing indexes are logged as warnings only.
"""

from __future__ import annotations

from time import perf_counter
from typing import Any

from app.core.constants import CONSTRAINTS_PIPELINE
from app.core.exceptions import ConfigurationError
from app.core.logging import get_logger, log_event
from app.core.time import utc_now
from app.loaders.constraints import ConstraintVerifier
from app.loaders.indexes import IndexVerifier
from app.pipelines.base import BasePipeline, PipelineResult

LOGGER = get_logger(__name__)


class ConstraintsPipeline(BasePipeline):
    """
    Verifies all required Neo4j constraints and performance indexes.

    Does not process warehouse sources.
    Raises ConfigurationError if any required constraint is absent.
    """

    pipeline_name = CONSTRAINTS_PIPELINE
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
            constraint_verifier = ConstraintVerifier(self._neo4j_client)
            index_verifier = IndexVerifier(self._neo4j_client)

            # Constraints — CRITICAL: raise on any missing
            constraint_results = constraint_verifier.verify_all()
            missing = [r for r in constraint_results if not r.present]
            if missing:
                missing_desc = [
                    f"{r.label}.{r.property_name} ({r.constraint_type})"
                    for r in missing
                ]
                raise ConfigurationError(
                    "Required Neo4j constraints are missing. "
                    "Run the graph migration before starting pipelines.",
                    missing_constraints=missing_desc,
                )

            log_event(
                self._logger,
                event_name="constraints_verified",
                total=len(constraint_results),
                all_present=True,
            )

            # Indexes — WARNING only
            index_results = index_verifier.verify_all()
            missing_indexes = [r for r in index_results if not r.present]
            if missing_indexes:
                missing_index_desc = [
                    f"{r.label}.{r.property_name}" for r in missing_indexes
                ]
                log_event(
                    self._logger,
                    event_name="indexes_missing_warning",
                    missing=missing_index_desc,
                    message="Missing indexes may degrade load performance",
                )

            result.status = "completed"

        except ConfigurationError:
            result.status = "failed"
            raise

        except Exception as exc:
            result.status = "failed"
            result.error_messages.append(str(exc))
            log_event(self._logger, event_name="constraints_pipeline_error", error=str(exc))

        finally:
            result.finished_at = utc_now().isoformat()
            result.duration_seconds = perf_counter() - started
            self._log_pipeline_finished(result)

        return result
