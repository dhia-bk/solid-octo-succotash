"""
Model/version registry repository for Project Pulse Knowledge Graph.

Purpose:
- persist model and analytics version run metadata
- support latest-version and historical lookup patterns
- centralize semver validation and compatibility storage
- provide durable registry records for analytics and inference runs

This module must not contain:
- analytics computation logic
- inference logic
- model training logic
- pipeline orchestration logic
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from app.core.exceptions import MetadataDatabaseError, ModelVersionError
from app.core.logging import ProjectPulseLoggerAdapter, get_logger, log_event
from app.core.security import sanitize_config_payload
from app.core.time import utc_now
from app.core.versioning import (
    assert_model_version_matches_config,
    validate_semver,
)
from app.db.metadata_db import MetadataDBClient

MODEL_REGISTRY_TABLE = "model_registry"

STATUS_PENDING = "pending"
STATUS_RUNNING = "running"
STATUS_SUCCEEDED = "succeeded"
STATUS_FAILED = "failed"
STATUS_DEPRECATED = "deprecated"

MODEL_RUN_STATUSES: tuple[str, ...] = (
    STATUS_PENDING,
    STATUS_RUNNING,
    STATUS_SUCCEEDED,
    STATUS_FAILED,
    STATUS_DEPRECATED,
)


@dataclass(slots=True)
class ModelRegistryRecord:
    """
    Normalized model registry record returned by the repository.
    """

    run_id: str
    model_type: str
    logical_version: str
    config_version: str | None
    status: str
    artifact_uri: str | None
    compatibility_metadata: dict[str, Any]
    metrics_summary: dict[str, Any]
    created_at: str | None
    updated_at: str | None


class ModelRegistryRepository:
    """
    Repository for persisted model/version metadata and run history.
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

    def register_model_run(
        self,
        *,
        model_type: str,
        logical_version: str,
        run_id: str,
        config_version: str | None = None,
        status: str = STATUS_SUCCEEDED,
        artifact_uri: str | None = None,
        compatibility_metadata: dict[str, Any] | None = None,
        metrics_summary: dict[str, Any] | None = None,
    ) -> ModelRegistryRecord:
        """
        Insert a new model/version run record.
        """
        self._validate_model_type(model_type)
        self._validate_run_id(run_id)
        self._validate_status(status)

        normalized_logical_version = validate_semver(logical_version)
        normalized_config_version = (
            validate_semver(config_version) if config_version is not None else None
        )

        compatibility_payload = self._sanitize_payload(compatibility_metadata or {})
        metrics_payload = self._sanitize_payload(metrics_summary or {})
        created_at = utc_now().isoformat()

        statement = f"""
        INSERT INTO {MODEL_REGISTRY_TABLE} (
            run_id,
            model_type,
            logical_version,
            config_version,
            status,
            artifact_uri,
            compatibility_metadata_json,
            metrics_summary_json,
            created_at,
            updated_at
        )
        VALUES (
            :run_id,
            :model_type,
            :logical_version,
            :config_version,
            :status,
            :artifact_uri,
            :compatibility_metadata_json,
            :metrics_summary_json,
            :created_at,
            :updated_at
        )
        """

        params = {
            "run_id": run_id.strip(),
            "model_type": model_type.strip(),
            "logical_version": normalized_logical_version,
            "config_version": normalized_config_version,
            "status": status,
            "artifact_uri": self._normalize_optional_string(artifact_uri),
            "compatibility_metadata_json": json.dumps(
                compatibility_payload,
                sort_keys=True,
            ),
            "metrics_summary_json": json.dumps(metrics_payload, sort_keys=True),
            "created_at": created_at,
            "updated_at": created_at,
        }

        try:
            self._metadata_db.execute(statement, params)

            log_event(
                self._logger,
                event_name="model_registry_run_registered",
                message="Model registry run registered",
                model_type=model_type,
                logical_version=normalized_logical_version,
                run_id=run_id,
                status=status,
            )

            record = self.get_run(run_id)
            if record is None:
                raise MetadataDatabaseError(
                    "Model run registration completed but record could not be reloaded",
                    run_id=run_id,
                    model_type=model_type,
                )
            return record
        except Exception as exc:  # noqa: BLE001
            if isinstance(exc, (ModelVersionError, MetadataDatabaseError)):
                raise
            raise self._repository_error(
                "Failed to register model run",
                exc,
                run_id=run_id,
                model_type=model_type,
            ) from exc

    def upsert_model_version(
        self,
        *,
        model_type: str,
        logical_version: str,
        run_id: str,
        config_version: str | None = None,
        status: str = STATUS_SUCCEEDED,
        artifact_uri: str | None = None,
        compatibility_metadata: dict[str, Any] | None = None,
        metrics_summary: dict[str, Any] | None = None,
    ) -> ModelRegistryRecord:
        """
        Insert or update a model/version run record by run_id.
        """
        self._validate_model_type(model_type)
        self._validate_run_id(run_id)
        self._validate_status(status)

        normalized_logical_version = validate_semver(logical_version)
        normalized_config_version = (
            validate_semver(config_version) if config_version is not None else None
        )
        compatibility_payload = self._sanitize_payload(compatibility_metadata or {})
        metrics_payload = self._sanitize_payload(metrics_summary or {})
        updated_at = utc_now().isoformat()

        statement = f"""
        INSERT INTO {MODEL_REGISTRY_TABLE} (
            run_id,
            model_type,
            logical_version,
            config_version,
            status,
            artifact_uri,
            compatibility_metadata_json,
            metrics_summary_json,
            created_at,
            updated_at
        )
        VALUES (
            :run_id,
            :model_type,
            :logical_version,
            :config_version,
            :status,
            :artifact_uri,
            :compatibility_metadata_json,
            :metrics_summary_json,
            :created_at,
            :updated_at
        )
        ON DUPLICATE KEY UPDATE
            model_type = VALUES(model_type),
            logical_version = VALUES(logical_version),
            config_version = VALUES(config_version),
            status = VALUES(status),
            artifact_uri = VALUES(artifact_uri),
            compatibility_metadata_json = VALUES(compatibility_metadata_json),
            metrics_summary_json = VALUES(metrics_summary_json),
            updated_at = VALUES(updated_at)
        """

        params = {
            "run_id": run_id.strip(),
            "model_type": model_type.strip(),
            "logical_version": normalized_logical_version,
            "config_version": normalized_config_version,
            "status": status,
            "artifact_uri": self._normalize_optional_string(artifact_uri),
            "compatibility_metadata_json": json.dumps(
                compatibility_payload,
                sort_keys=True,
            ),
            "metrics_summary_json": json.dumps(metrics_payload, sort_keys=True),
            "created_at": updated_at,
            "updated_at": updated_at,
        }

        try:
            self._metadata_db.execute(statement, params)

            log_event(
                self._logger,
                event_name="model_registry_version_upserted",
                message="Model registry version upsert completed",
                model_type=model_type,
                logical_version=normalized_logical_version,
                run_id=run_id,
                status=status,
            )

            record = self.get_run(run_id)
            if record is None:
                raise MetadataDatabaseError(
                    "Model version upsert completed but record could not be reloaded",
                    run_id=run_id,
                    model_type=model_type,
                )
            return record
        except Exception as exc:  # noqa: BLE001
            if isinstance(exc, (ModelVersionError, MetadataDatabaseError)):
                raise
            raise self._repository_error(
                "Failed to upsert model version",
                exc,
                run_id=run_id,
                model_type=model_type,
            ) from exc

    def get_run(self, run_id: str) -> ModelRegistryRecord | None:
        """
        Fetch a model registry record by run_id.
        """
        self._validate_run_id(run_id)

        statement = f"""
        SELECT
            run_id,
            model_type,
            logical_version,
            config_version,
            status,
            artifact_uri,
            compatibility_metadata_json,
            metrics_summary_json,
            created_at,
            updated_at
        FROM {MODEL_REGISTRY_TABLE}
        WHERE run_id = :run_id
        LIMIT 1
        """

        try:
            row = self._metadata_db.fetch_one(statement, {"run_id": run_id.strip()})
            record = self._to_record(row) if row is not None else None

            log_event(
                self._logger,
                event_name="model_registry_run_read",
                message="Model registry run read completed",
                run_id=run_id,
                found=record is not None,
            )
            return record
        except Exception as exc:  # noqa: BLE001
            raise self._repository_error(
                "Failed to read model registry run",
                exc,
                run_id=run_id,
            ) from exc

    def get_latest(
        self,
        model_type: str,
        *,
        status: str = STATUS_SUCCEEDED,
    ) -> ModelRegistryRecord | None:
        """
        Fetch the latest record for a model type, optionally filtered by status.
        """
        self._validate_model_type(model_type)
        self._validate_status(status)

        statement = f"""
        SELECT
            run_id,
            model_type,
            logical_version,
            config_version,
            status,
            artifact_uri,
            compatibility_metadata_json,
            metrics_summary_json,
            created_at,
            updated_at
        FROM {MODEL_REGISTRY_TABLE}
        WHERE model_type = :model_type
          AND status = :status
        ORDER BY created_at DESC, run_id DESC
        LIMIT 1
        """

        try:
            row = self._metadata_db.fetch_one(
                statement,
                {
                    "model_type": model_type.strip(),
                    "status": status,
                },
            )
            record = self._to_record(row) if row is not None else None

            log_event(
                self._logger,
                event_name="model_registry_latest_read",
                message="Latest model registry record lookup completed",
                model_type=model_type,
                status=status,
                found=record is not None,
            )
            return record
        except Exception as exc:  # noqa: BLE001
            raise self._repository_error(
                "Failed to read latest model version",
                exc,
                model_type=model_type,
                status=status,
            ) from exc

    def list_versions(
        self,
        *,
        model_type: str | None = None,
        status: str | None = None,
        limit: int | None = None,
    ) -> list[ModelRegistryRecord]:
        """
        List model registry versions with optional filtering.
        """
        if model_type is not None:
            self._validate_model_type(model_type)
        if status is not None:
            self._validate_status(status)
        if limit is not None and limit <= 0:
            raise MetadataDatabaseError("limit must be positive", limit=limit)

        filters: list[str] = []
        params: dict[str, Any] = {}

        if model_type is not None:
            filters.append("model_type = :model_type")
            params["model_type"] = model_type.strip()

        if status is not None:
            filters.append("status = :status")
            params["status"] = status

        where_clause = f"WHERE {' AND '.join(filters)}" if filters else ""
        limit_clause = "LIMIT :limit" if limit is not None else ""

        if limit is not None:
            params["limit"] = limit

        statement = f"""
        SELECT
            run_id,
            model_type,
            logical_version,
            config_version,
            status,
            artifact_uri,
            compatibility_metadata_json,
            metrics_summary_json,
            created_at,
            updated_at
        FROM {MODEL_REGISTRY_TABLE}
        {where_clause}
        ORDER BY created_at DESC, run_id DESC
        {limit_clause}
        """

        try:
            rows = self._metadata_db.fetch_all(statement, params)
            records = [self._to_record(row) for row in rows]

            log_event(
                self._logger,
                event_name="model_registry_versions_listed",
                message="Model registry version list completed",
                model_type=model_type,
                status=status,
                record_count=len(records),
            )
            return records
        except Exception as exc:  # noqa: BLE001
            raise self._repository_error(
                "Failed to list model versions",
                exc,
                model_type=model_type,
                status=status,
            ) from exc

    def assert_compatible_with_config(
        self,
        *,
        model_type: str,
        logical_version: str,
        config_version: str,
    ) -> None:
        """
        Validate compatibility between a model logical version and a config version.
        """
        self._validate_model_type(model_type)
        normalized_logical_version = validate_semver(logical_version)
        normalized_config_version = validate_semver(config_version)

        try:
            assert_model_version_matches_config(
                normalized_logical_version,
                normalized_config_version,
            )
            log_event(
                self._logger,
                event_name="model_registry_compatibility_validated",
                message="Model/config version compatibility validated",
                model_type=model_type,
                logical_version=normalized_logical_version,
                config_version=normalized_config_version,
            )
        except Exception as exc:  # noqa: BLE001
            if isinstance(exc, ModelVersionError):
                log_event(
                    self._logger,
                    event_name="model_registry_compatibility_failed",
                    level=40,
                    message="Model/config version compatibility failed",
                    model_type=model_type,
                    logical_version=normalized_logical_version,
                    config_version=normalized_config_version,
                    error_type=type(exc).__name__,
                )
                raise

            raise ModelVersionError(
                "Failed to validate model/config compatibility",
                model_type=model_type,
                logical_version=normalized_logical_version,
                config_version=normalized_config_version,
                error_type=type(exc).__name__,
            ) from exc

    @staticmethod
    def _validate_model_type(model_type: str) -> None:
        if not model_type or not model_type.strip():
            raise ModelVersionError("model_type must not be empty")

    @staticmethod
    def _validate_run_id(run_id: str) -> None:
        if not run_id or not run_id.strip():
            raise ModelVersionError("run_id must not be empty")

    @staticmethod
    def _validate_status(status: str) -> None:
        if status not in MODEL_RUN_STATUSES:
            raise ModelVersionError(
                "Unsupported model run status",
                status=status,
                supported_statuses=MODEL_RUN_STATUSES,
            )

    @staticmethod
    def _normalize_optional_string(value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @staticmethod
    def _sanitize_payload(payload: dict[str, Any]) -> dict[str, Any]:
        return sanitize_config_payload(payload)

    @staticmethod
    def _decode_json_field(value: Any) -> dict[str, Any]:
        if value in (None, ""):
            return {}
        if isinstance(value, dict):
            return value
        return json.loads(value)

    @classmethod
    def _to_record(cls, row: dict[str, Any]) -> ModelRegistryRecord:
        def _iso(value: Any) -> str | None:
            if value is None:
                return None
            if hasattr(value, "isoformat"):
                return value.isoformat()
            return str(value)

        return ModelRegistryRecord(
            run_id=str(row["run_id"]),
            model_type=str(row["model_type"]),
            logical_version=str(row["logical_version"]),
            config_version=row.get("config_version"),
            status=str(row["status"]),
            artifact_uri=row.get("artifact_uri"),
            compatibility_metadata=cls._decode_json_field(row.get("compatibility_metadata_json")),
            metrics_summary=cls._decode_json_field(row.get("metrics_summary_json")),
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
