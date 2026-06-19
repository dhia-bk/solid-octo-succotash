"""
Job run audit repository for Project Pulse Knowledge Graph.

Purpose:
- persist durable job and pipeline run history
- support run lifecycle updates (pending/running/succeeded/failed/canceled)
- provide query access for run diagnostics and operational dashboards
- centralize logging and error handling for run records

This module must not contain:
- pipeline orchestration logic
- retry policy logic
- service/API behavior
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from app.core.constants import (
    DEV,
    KEY_ENV,
    KEY_ERROR,
    KEY_FINISHED_AT,
    KEY_JOB_NAME,
    KEY_PIPELINE_NAME,
    KEY_RUN_ID,
    KEY_STARTED_AT,
    KEY_STATUS,
    KEY_VERSION,
)
from app.core.exceptions import MetadataDatabaseError
from app.core.logging import ProjectPulseLoggerAdapter, get_logger, log_event
from app.core.security import sanitize_config_payload
from app.core.time import ensure_utc_datetime, utc_now, parse_iso_datetime
from app.db.metadata_db import MetadataDBClient


JOB_RUNS_TABLE = "job_runs"

STATUS_PENDING = "pending"
STATUS_RUNNING = "running"
STATUS_SUCCEEDED = "succeeded"
STATUS_FAILED = "failed"
STATUS_CANCELED = "canceled"

RUN_STATUSES: tuple[str, ...] = (
    STATUS_PENDING,
    STATUS_RUNNING,
    STATUS_SUCCEEDED,
    STATUS_FAILED,
    STATUS_CANCELED,
)


@dataclass(slots=True)
class JobRunRecord:
    """
    Normalized job run record returned by the repository.
    """

    run_id: str
    job_name: str | None
    pipeline_name: str | None
    status: str
    started_at: str | None
    finished_at: str | None
    duration_ms: int | None
    environment: str | None
    version: str | None
    error_message: str | None
    metadata: dict[str, Any]
    created_at: str | None
    updated_at: str | None


class JobRunRepository:
    """
    Repository for durable job and pipeline run audit records.
    """

    def __init__(
        self,
        metadata_db: MetadataDBClient,
        *,
        logger: ProjectPulseLoggerAdapter | None = None,
    ) -> None:
        self._metadata_db = metadata_db
        self._logger = logger or get_logger(__name__)

    @property
    def metadata_db(self) -> MetadataDBClient:
        return self._metadata_db

    @property
    def logger(self) -> ProjectPulseLoggerAdapter:
        return self._logger

    def create_run(
        self,
        *,
        run_id: str,
        job_name: str | None = None,
        pipeline_name: str | None = None,
        status: str = STATUS_PENDING,
        environment: str = DEV,
        version: str | None = None,
        started_at: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> JobRunRecord:
        """
        Create a new job/pipeline run record.
        """
        self._validate_run_id(run_id)
        self._validate_name_pair(job_name=job_name, pipeline_name=pipeline_name)
        self._validate_status(status)

        now = utc_now().isoformat()
        normalized_started_at = self._normalize_optional_datetime(started_at)
        metadata_payload = self._sanitize_metadata(metadata or {})

        statement = f"""
        INSERT INTO {JOB_RUNS_TABLE} (
            run_id,
            job_name,
            pipeline_name,
            status,
            started_at,
            finished_at,
            duration_ms,
            environment,
            version,
            error_message,
            metadata_json,
            created_at,
            updated_at
        )
        VALUES (
            :run_id,
            :job_name,
            :pipeline_name,
            :status,
            :started_at,
            :finished_at,
            :duration_ms,
            :environment,
            :version,
            :error_message,
            :metadata_json,
            :created_at,
            :updated_at
        )
        """

        params = {
            "run_id": run_id.strip(),
            "job_name": self._normalize_optional_string(job_name),
            "pipeline_name": self._normalize_optional_string(pipeline_name),
            "status": status,
            "started_at": normalized_started_at,
            "finished_at": None,
            "duration_ms": None,
            "environment": environment.strip(),
            "version": self._normalize_optional_string(version),
            "error_message": None,
            "metadata_json": json.dumps(metadata_payload, sort_keys=True),
            "created_at": now,
            "updated_at": now,
        }

        try:
            self._metadata_db.execute(statement, params)

            log_event(
                self._logger,
                event_name="job_run_created",
                message="Job run created",
                run_id=run_id,
                job_name=job_name,
                pipeline_name=pipeline_name,
                status=status,
                environment=environment,
                version=version,
            )
            record = self.get_run(run_id)
            if record is None:
                raise MetadataDatabaseError(
                    "Run creation completed but record could not be reloaded",
                    run_id=run_id,
                )
            return record
        except Exception as exc:  # noqa: BLE001
            if isinstance(exc, MetadataDatabaseError):
                raise
            raise self._repository_error(
                "Failed to create job run",
                exc,
                run_id=run_id,
                job_name=job_name,
                pipeline_name=pipeline_name,
            ) from exc

    def mark_running(
        self,
        run_id: str,
        *,
        started_at: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> JobRunRecord:
        """
        Mark a run as running and optionally set/refresh started_at.
        """
        return self._update_run_state(
            run_id,
            status=STATUS_RUNNING,
            started_at=self._normalize_optional_datetime(started_at) or utc_now().isoformat(),
            metadata=metadata,
            log_event_name="job_run_marked_running",
            log_message="Job run marked running",
        )

    def mark_succeeded(
        self,
        run_id: str,
        *,
        finished_at: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> JobRunRecord:
        """
        Mark a run as succeeded.
        """
        return self._finalize_run(
            run_id,
            status=STATUS_SUCCEEDED,
            finished_at=finished_at,
            metadata=metadata,
            error_message=None,
            log_event_name="job_run_marked_succeeded",
            log_message="Job run marked succeeded",
        )

    def mark_failed(
        self,
        run_id: str,
        *,
        finished_at: str | None = None,
        error_message: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> JobRunRecord:
        """
        Mark a run as failed.
        """
        return self._finalize_run(
            run_id,
            status=STATUS_FAILED,
            finished_at=finished_at,
            metadata=metadata,
            error_message=self._normalize_optional_string(error_message),
            log_event_name="job_run_marked_failed",
            log_message="Job run marked failed",
        )

    def mark_canceled(
        self,
        run_id: str,
        *,
        finished_at: str | None = None,
        error_message: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> JobRunRecord:
        """
        Mark a run as canceled.
        """
        return self._finalize_run(
            run_id,
            status=STATUS_CANCELED,
            finished_at=finished_at,
            metadata=metadata,
            error_message=self._normalize_optional_string(error_message),
            log_event_name="job_run_marked_canceled",
            log_message="Job run marked canceled",
        )

    def get_run(self, run_id: str) -> JobRunRecord | None:
        """
        Fetch a run record by run_id.
        """
        self._validate_run_id(run_id)

        statement = f"""
        SELECT
            run_id,
            job_name,
            pipeline_name,
            status,
            started_at,
            finished_at,
            duration_ms,
            environment,
            version,
            error_message,
            metadata_json,
            created_at,
            updated_at
        FROM {JOB_RUNS_TABLE}
        WHERE run_id = :run_id
        LIMIT 1
        """

        try:
            row = self._metadata_db.fetch_one(statement, {"run_id": run_id.strip()})
            record = self._to_record(row) if row is not None else None

            log_event(
                self._logger,
                event_name="job_run_read",
                message="Job run read completed",
                run_id=run_id,
                found=record is not None,
            )
            return record
        except Exception as exc:  # noqa: BLE001
            raise self._repository_error(
                "Failed to read job run",
                exc,
                run_id=run_id,
            ) from exc

    def list_runs(
        self,
        *,
        job_name: str | None = None,
        pipeline_name: str | None = None,
        status: str | None = None,
        started_after: str | None = None,
        started_before: str | None = None,
        limit: int | None = None,
    ) -> list[JobRunRecord]:
        """
        List runs with optional filtering by job name, pipeline name, status,
        and started_at bounds.
        """
        if status is not None:
            self._validate_status(status)

        filters: list[str] = []
        params: dict[str, Any] = {}

        if job_name is not None:
            filters.append("job_name = :job_name")
            params["job_name"] = job_name.strip()

        if pipeline_name is not None:
            filters.append("pipeline_name = :pipeline_name")
            params["pipeline_name"] = pipeline_name.strip()

        if status is not None:
            filters.append("status = :status")
            params["status"] = status

        if started_after is not None:
            filters.append("started_at >= :started_after")
            params["started_after"] = self._normalize_required_datetime(started_after)

        if started_before is not None:
            filters.append("started_at <= :started_before")
            params["started_before"] = self._normalize_required_datetime(started_before)

        where_clause = f"WHERE {' AND '.join(filters)}" if filters else ""
        limit_clause = "LIMIT :limit" if limit is not None else ""

        if limit is not None:
            if limit <= 0:
                raise MetadataDatabaseError("limit must be positive", limit=limit)
            params["limit"] = limit

        statement = f"""
        SELECT
            run_id,
            job_name,
            pipeline_name,
            status,
            started_at,
            finished_at,
            duration_ms,
            environment,
            version,
            error_message,
            metadata_json,
            created_at,
            updated_at
        FROM {JOB_RUNS_TABLE}
        {where_clause}
        ORDER BY created_at DESC, run_id DESC
        {limit_clause}
        """

        try:
            rows = self._metadata_db.fetch_all(statement, params)
            records = [self._to_record(row) for row in rows]

            log_event(
                self._logger,
                event_name="job_run_list",
                message="Job run list completed",
                job_name=job_name,
                pipeline_name=pipeline_name,
                status=status,
                record_count=len(records),
            )
            return records
        except Exception as exc:  # noqa: BLE001
            raise self._repository_error(
                "Failed to list job runs",
                exc,
                job_name=job_name,
                pipeline_name=pipeline_name,
                status=status,
            ) from exc

    def _update_run_state(
        self,
        run_id: str,
        *,
        status: str,
        started_at: str | None = None,
        finished_at: str | None = None,
        duration_ms: int | None = None,
        error_message: str | None = None,
        metadata: dict[str, Any] | None = None,
        log_event_name: str,
        log_message: str,
    ) -> JobRunRecord:
        self._validate_run_id(run_id)
        self._validate_status(status)

        existing = self.get_run(run_id)
        if existing is None:
            raise MetadataDatabaseError("Run not found", run_id=run_id)

        merged_metadata = self._merge_metadata(existing.metadata, metadata)
        updated_at = utc_now().isoformat()

        statement = f"""
        UPDATE {JOB_RUNS_TABLE}
        SET
            status = :status,
            started_at = :started_at,
            finished_at = :finished_at,
            duration_ms = :duration_ms,
            error_message = :error_message,
            metadata_json = :metadata_json,
            updated_at = :updated_at
        WHERE run_id = :run_id
        """

        params = {
            "run_id": run_id.strip(),
            "status": status,
            "started_at": started_at or existing.started_at,
            "finished_at": finished_at or existing.finished_at,
            "duration_ms": duration_ms,
            "error_message": error_message,
            "metadata_json": json.dumps(merged_metadata, sort_keys=True),
            "updated_at": updated_at,
        }

        try:
            self._metadata_db.execute(statement, params)

            log_event(
                self._logger,
                event_name=log_event_name,
                message=log_message,
                run_id=run_id,
                status=status,
            )

            record = self.get_run(run_id)
            if record is None:
                raise MetadataDatabaseError(
                    "Run state update completed but record could not be reloaded",
                    run_id=run_id,
                )
            return record
        except Exception as exc:  # noqa: BLE001
            if isinstance(exc, MetadataDatabaseError):
                raise
            raise self._repository_error(
                "Failed to update run state",
                exc,
                run_id=run_id,
                status=status,
            ) from exc

    def _finalize_run(
        self,
        run_id: str,
        *,
        status: str,
        finished_at: str | None,
        metadata: dict[str, Any] | None,
        error_message: str | None,
        log_event_name: str,
        log_message: str,
    ) -> JobRunRecord:
        existing = self.get_run(run_id)
        if existing is None:
            raise MetadataDatabaseError("Run not found", run_id=run_id)

        normalized_finished_at = (
            self._normalize_optional_datetime(finished_at) or utc_now().isoformat()
        )
        duration_ms = self._compute_duration_ms(
            started_at=existing.started_at,
            finished_at=normalized_finished_at,
        )

        return self._update_run_state(
            run_id,
            status=status,
            started_at=existing.started_at,
            finished_at=normalized_finished_at,
            duration_ms=duration_ms,
            error_message=error_message,
            metadata=metadata,
            log_event_name=log_event_name,
            log_message=log_message,
        )

    @staticmethod
    def _compute_duration_ms(
        *,
        started_at,
        finished_at,
    ) -> int | None:
        if started_at is None or finished_at is None:
            return None

        started = ensure_utc_datetime(parse_iso_datetime(started_at))
        finished = ensure_utc_datetime(parse_iso_datetime(finished_at))
        duration = int((finished - started).total_seconds() * 1000)
        return max(duration, 0)

    @staticmethod
    def _validate_run_id(run_id: str) -> None:
        if not run_id or not run_id.strip():
            raise MetadataDatabaseError("run_id must not be empty")

    @staticmethod
    def _validate_status(status: str) -> None:
        if status not in RUN_STATUSES:
            raise MetadataDatabaseError(
                "Unsupported run status",
                status=status,
                supported_statuses=RUN_STATUSES,
            )

    @staticmethod
    def _validate_name_pair(
        *,
        job_name: str | None,
        pipeline_name: str | None,
    ) -> None:
        if not (job_name and job_name.strip()) and not (pipeline_name and pipeline_name.strip()):
            raise MetadataDatabaseError(
                "At least one of job_name or pipeline_name must be provided"
            )

    @staticmethod
    def _normalize_optional_string(value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @staticmethod
    def _normalize_optional_datetime(value: str | None) -> str | None:
        if value is None:
            return None
        return ensure_utc_datetime(value).isoformat()

    @staticmethod
    def _normalize_required_datetime(value: str) -> str:
        return ensure_utc_datetime(value).isoformat()

    @staticmethod
    def _sanitize_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
        return sanitize_config_payload(metadata)

    def _merge_metadata(
        self,
        existing: dict[str, Any],
        incoming: dict[str, Any] | None,
    ) -> dict[str, Any]:
        sanitized_incoming = self._sanitize_metadata(incoming or {})
        return {**existing, **sanitized_incoming}

    @staticmethod
    def _to_record(row: dict[str, Any]) -> JobRunRecord:
        raw_metadata = row.get("metadata_json")

        if raw_metadata in (None, ""):
            metadata: dict[str, Any] = {}
        elif isinstance(raw_metadata, dict):
            metadata = raw_metadata
        else:
            metadata = json.loads(raw_metadata)

        def _iso(value: Any) -> str | None:
            if value is None:
                return None
            if hasattr(value, "isoformat"):
                return value.isoformat()
            return str(value)

        return JobRunRecord(
            run_id=str(row[KEY_RUN_ID]),
            job_name=row.get(KEY_JOB_NAME),
            pipeline_name=row.get(KEY_PIPELINE_NAME),
            status=str(row[KEY_STATUS]),
            started_at=_iso(row.get(KEY_STARTED_AT)),
            finished_at=_iso(row.get(KEY_FINISHED_AT)),
            duration_ms=row.get("duration_ms"),
            environment=row.get(KEY_ENV),
            version=row.get(KEY_VERSION),
            error_message=row.get(KEY_ERROR),
            metadata=metadata,
            created_at=_iso(row.get("created_at")),
            updated_at=_iso(row.get("updated_at")),
        )

    @staticmethod
    def _repository_error(
        message: str,
        exc: Exception,
        **context: Any,
    ) -> MetadataDatabaseError:
        return MetadataDatabaseError(
            message,
            error_type=type(exc).__name__,
            **context,
        )


# A matching minimal metadata table would look roughly like this:

# CREATE TABLE model_registry (
#     run_id VARCHAR(255) NOT NULL PRIMARY KEY,
#     model_type VARCHAR(255) NOT NULL,
#     logical_version VARCHAR(64) NOT NULL,
#     config_version VARCHAR(64) NULL,
#     status VARCHAR(64) NOT NULL,
#     artifact_uri TEXT NULL,
#     compatibility_metadata_json JSON NULL,
#     metrics_summary_json JSON NULL,
#     created_at DATETIME NOT NULL,
#     updated_at DATETIME NOT NULL,
#     INDEX idx_model_registry_model_type (model_type),
#     INDEX idx_model_registry_status (status),
#     INDEX idx_model_registry_created_at (created_at),
#     INDEX idx_model_registry_model_status_created (model_type, status, created_at)
# );

# A few practical notes:

# register_model_run() is a straight insert; upsert_model_version() is the safe overwrite/update variant if you want idempotent reruns by run_id.

# get_latest() defaults to the latest succeeded run, which is usually the most useful operational behavior.

# Compatibility is exposed as a validation helper, but the repository does not infer business meaning beyond storing and checking versions.

# Both compatibility_metadata and metrics_summary are sanitized before persistence so secrets/config fragments do not get written raw.
