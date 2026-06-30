"""
Checkpoint repository for Project Pulse Knowledge Graph.

Purpose:
- persist and retrieve incremental sync checkpoint state
- normalize watermark values consistently
- support timestamp, numeric, and full-refresh checkpoint strategies
- centralize checkpoint logging and error handling

This module must not contain:
- pipeline orchestration logic
- extractor logic
- business rules for when checkpoints should be written
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from app.core.constants import (
    CHECKPOINT_STRATEGIES,
    CHECKPOINT_STRATEGY_FULL_REFRESH,
    CHECKPOINT_STRATEGY_NUMERIC_WATERMARK,
    CHECKPOINT_STRATEGY_TIMESTAMP_WATERMARK,
    DEFAULT_CHECKPOINT_NAMESPACE,
)
from app.core.exceptions import CheckpointError
from app.core.logging import ProjectPulseLoggerAdapter, get_logger, log_event
from app.core.time import is_null_watermark, normalize_watermark, utc_now
from app.db.metadata_db import MetadataDBClient

CHECKPOINTS_TABLE = "checkpoints"


@dataclass(slots=True)
class CheckpointRecord:
    """
    Normalized checkpoint record returned by the repository.
    """

    namespace: str
    pipeline_name: str
    source_name: str
    checkpoint_strategy: str
    watermark_value: str | None
    last_successful_run_id: str | None
    metadata: dict[str, Any]
    updated_at: str | None


class CheckpointRepository:
    """
    Repository for persisted incremental checkpoint state.
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

    def get_checkpoint(
        self,
        namespace: str = DEFAULT_CHECKPOINT_NAMESPACE,
        pipeline_name: str = "",
        source_name: str = "",
    ) -> CheckpointRecord | None:
        """
        Fetch a single checkpoint by namespace + pipeline + source.
        """
        self._validate_required_key("namespace", namespace)
        self._validate_required_key("pipeline_name", pipeline_name)
        self._validate_required_key("source_name", source_name)

        statement = f"""
        SELECT
            namespace,
            pipeline_name,
            source_name,
            checkpoint_strategy,
            watermark_value,
            last_successful_run_id,
            metadata_json,
            updated_at
        FROM {CHECKPOINTS_TABLE}
        WHERE namespace = :namespace
          AND pipeline_name = :pipeline_name
          AND source_name = :source_name
        LIMIT 1
        """

        try:
            row = self._metadata_db.fetch_one(
                statement,
                {
                    "namespace": namespace,
                    "pipeline_name": pipeline_name,
                    "source_name": source_name,
                },
            )

            record = self._to_record(row) if row is not None else None

            log_event(
                self._logger,
                event_name="checkpoint_read",
                message="Checkpoint read completed",
                namespace=namespace,
                pipeline_name=pipeline_name,
                source_name=source_name,
                found=record is not None,
            )
            return record
        except Exception as exc:  # noqa: BLE001
            raise self._repository_error(
                "Failed to read checkpoint",
                exc,
                namespace=namespace,
                pipeline_name=pipeline_name,
                source_name=source_name,
            ) from exc

    def list_checkpoints(
        self,
        *,
        namespace: str | None = None,
        pipeline_name: str | None = None,
    ) -> list[CheckpointRecord]:
        """
        List checkpoints optionally filtered by namespace and/or pipeline name.
        """
        filters: list[str] = []
        params: dict[str, Any] = {}

        if namespace is not None:
            filters.append("namespace = :namespace")
            params["namespace"] = namespace.strip()

        if pipeline_name is not None:
            filters.append("pipeline_name = :pipeline_name")
            params["pipeline_name"] = pipeline_name.strip()

        where_clause = f"WHERE {' AND '.join(filters)}" if filters else ""

        statement = f"""
        SELECT
            namespace,
            pipeline_name,
            source_name,
            checkpoint_strategy,
            watermark_value,
            last_successful_run_id,
            metadata_json,
            updated_at
        FROM {CHECKPOINTS_TABLE}
        {where_clause}
        ORDER BY namespace, pipeline_name, source_name
        """

        try:
            rows = self._metadata_db.fetch_all(statement, params)
            records = [self._to_record(row) for row in rows]

            log_event(
                self._logger,
                event_name="checkpoint_list",
                message="Checkpoint list completed",
                namespace=namespace,
                pipeline_name=pipeline_name,
                record_count=len(records),
            )
            return records
        except Exception as exc:  # noqa: BLE001
            raise self._repository_error(
                "Failed to list checkpoints",
                exc,
                namespace=namespace,
                pipeline_name=pipeline_name,
            ) from exc

    def upsert_checkpoint(
        self,
        *,
        namespace: str = DEFAULT_CHECKPOINT_NAMESPACE,
        pipeline_name: str,
        source_name: str,
        checkpoint_strategy: str,
        watermark_value: Any = None,
        last_successful_run_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> CheckpointRecord:
        """
        Insert or update a checkpoint row.
        """
        self._validate_required_key("namespace", namespace)
        self._validate_required_key("pipeline_name", pipeline_name)
        self._validate_required_key("source_name", source_name)
        self._validate_strategy(checkpoint_strategy)

        normalized_watermark = self._normalize_watermark_for_storage(
            checkpoint_strategy,
            watermark_value,
        )
        metadata_payload = metadata or {}
        updated_at = utc_now().isoformat()

        statement = f"""
        INSERT INTO {CHECKPOINTS_TABLE} (
            namespace,
            pipeline_name,
            source_name,
            checkpoint_strategy,
            watermark_value,
            last_successful_run_id,
            metadata_json,
            updated_at
        )
        VALUES (
            :namespace,
            :pipeline_name,
            :source_name,
            :checkpoint_strategy,
            :watermark_value,
            :last_successful_run_id,
            :metadata_json,
            :updated_at
        )
        ON CONFLICT (namespace, pipeline_name, source_name) DO UPDATE SET
            checkpoint_strategy = EXCLUDED.checkpoint_strategy,
            watermark_value = EXCLUDED.watermark_value,
            last_successful_run_id = EXCLUDED.last_successful_run_id,
            metadata_json = EXCLUDED.metadata_json,
            updated_at = EXCLUDED.updated_at
        """

        params = {
            "namespace": namespace.strip(),
            "pipeline_name": pipeline_name.strip(),
            "source_name": source_name.strip(),
            "checkpoint_strategy": checkpoint_strategy,
            "watermark_value": normalized_watermark,
            "last_successful_run_id": self._normalize_optional_string(last_successful_run_id),
            "metadata_json": json.dumps(metadata_payload, sort_keys=True),
            "updated_at": updated_at,
        }

        try:
            self._metadata_db.execute(statement, params)

            log_event(
                self._logger,
                event_name="checkpoint_upsert",
                message="Checkpoint upsert completed",
                namespace=namespace,
                pipeline_name=pipeline_name,
                source_name=source_name,
                checkpoint_strategy=checkpoint_strategy,
                has_watermark=normalized_watermark is not None,
            )

            record = self.get_checkpoint(
                namespace=namespace,
                pipeline_name=pipeline_name,
                source_name=source_name,
            )
            if record is None:
                raise CheckpointError(
                    "Checkpoint upsert completed but record could not be reloaded",
                    namespace=namespace,
                    pipeline_name=pipeline_name,
                    source_name=source_name,
                )
            return record
        except Exception as exc:  # noqa: BLE001
            if isinstance(exc, CheckpointError):
                raise
            raise self._repository_error(
                "Failed to upsert checkpoint",
                exc,
                namespace=namespace,
                pipeline_name=pipeline_name,
                source_name=source_name,
                checkpoint_strategy=checkpoint_strategy,
            ) from exc

    def delete_checkpoint(
        self,
        *,
        namespace: str = DEFAULT_CHECKPOINT_NAMESPACE,
        pipeline_name: str,
        source_name: str,
    ) -> bool:
        """
        Delete a checkpoint row if it exists.
        """
        self._validate_required_key("namespace", namespace)
        self._validate_required_key("pipeline_name", pipeline_name)
        self._validate_required_key("source_name", source_name)

        statement = f"""
        DELETE FROM {CHECKPOINTS_TABLE}
        WHERE namespace = :namespace
          AND pipeline_name = :pipeline_name
          AND source_name = :source_name
        """

        try:
            affected = self._metadata_db.execute(
                statement,
                {
                    "namespace": namespace.strip(),
                    "pipeline_name": pipeline_name.strip(),
                    "source_name": source_name.strip(),
                },
            )

            deleted = affected > 0

            log_event(
                self._logger,
                event_name="checkpoint_delete",
                message="Checkpoint delete completed",
                namespace=namespace,
                pipeline_name=pipeline_name,
                source_name=source_name,
                deleted=deleted,
            )
            return deleted
        except Exception as exc:  # noqa: BLE001
            raise self._repository_error(
                "Failed to delete checkpoint",
                exc,
                namespace=namespace,
                pipeline_name=pipeline_name,
                source_name=source_name,
            ) from exc

    def reset_checkpoint(
        self,
        *,
        namespace: str = DEFAULT_CHECKPOINT_NAMESPACE,
        pipeline_name: str,
        source_name: str,
        metadata: dict[str, Any] | None = None,
        last_successful_run_id: str | None = None,
    ) -> CheckpointRecord:
        """
        Reset a checkpoint to full-refresh mode with a null watermark.
        """
        log_event(
            self._logger,
            event_name="checkpoint_reset",
            message="Checkpoint reset requested",
            namespace=namespace,
            pipeline_name=pipeline_name,
            source_name=source_name,
        )

        return self.upsert_checkpoint(
            namespace=namespace,
            pipeline_name=pipeline_name,
            source_name=source_name,
            checkpoint_strategy=CHECKPOINT_STRATEGY_FULL_REFRESH,
            watermark_value=None,
            last_successful_run_id=last_successful_run_id,
            metadata=metadata,
        )

    def _normalize_watermark_for_storage(
        self,
        checkpoint_strategy: str,
        watermark_value: Any,
    ) -> str | None:
        """
        Normalize watermark values to a stable storage format based on strategy.
        """
        if checkpoint_strategy == CHECKPOINT_STRATEGY_FULL_REFRESH:
            return None

        if checkpoint_strategy == CHECKPOINT_STRATEGY_TIMESTAMP_WATERMARK:
            if is_null_watermark(watermark_value):
                return None
            return normalize_watermark(watermark_value).isoformat()

        if checkpoint_strategy == CHECKPOINT_STRATEGY_NUMERIC_WATERMARK:
            if watermark_value is None:
                return None

            if isinstance(watermark_value, bool):
                raise CheckpointError(
                    "Boolean values are not valid numeric watermarks",
                    checkpoint_strategy=checkpoint_strategy,
                )

            if isinstance(watermark_value, (int, float)):
                return str(int(watermark_value))

            candidate = str(watermark_value).strip()
            if not candidate:
                return None
            if not candidate.lstrip("-").isdigit():
                raise CheckpointError(
                    "Numeric watermark must be an integer-like value",
                    checkpoint_strategy=checkpoint_strategy,
                    watermark_value=candidate,
                )
            return str(int(candidate))

        raise CheckpointError(
            "Unsupported checkpoint strategy",
            checkpoint_strategy=checkpoint_strategy,
        )

    def _validate_strategy(self, checkpoint_strategy: str) -> None:
        if checkpoint_strategy not in CHECKPOINT_STRATEGIES:
            raise CheckpointError(
                "Unsupported checkpoint strategy",
                checkpoint_strategy=checkpoint_strategy,
                supported_strategies=CHECKPOINT_STRATEGIES,
            )

    @staticmethod
    def _validate_required_key(field_name: str, value: str) -> None:
        if not value or not str(value).strip():
            raise CheckpointError(
                "Checkpoint key field must not be empty",
                field_name=field_name,
            )

    @staticmethod
    def _normalize_optional_string(value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @staticmethod
    def _to_record(row: dict[str, Any]) -> CheckpointRecord:
        raw_metadata = row.get("metadata_json")
        metadata: dict[str, Any]

        if raw_metadata in (None, ""):
            metadata = {}
        elif isinstance(raw_metadata, dict):
            metadata = raw_metadata
        else:
            metadata = json.loads(raw_metadata)

        return CheckpointRecord(
            namespace=str(row["namespace"]),
            pipeline_name=str(row["pipeline_name"]),
            source_name=str(row["source_name"]),
            checkpoint_strategy=str(row["checkpoint_strategy"]),
            watermark_value=row.get("watermark_value"),
            last_successful_run_id=row.get("last_successful_run_id"),
            metadata=metadata,
            updated_at=(
                row["updated_at"].isoformat()
                if hasattr(row.get("updated_at"), "isoformat")
                else row.get("updated_at")
            ),
        )

    @staticmethod
    def _repository_error(
        message: str,
        exc: Exception,
        **context: Any,
    ) -> CheckpointError:
        return CheckpointError(
            message,
            error_type=type(exc).__name__,
            **context,
        )


# A few practical notes:

# This assumes the metadata table is named checkpoints and includes a unique key on (namespace, pipeline_name, source_name) so ON DUPLICATE KEY UPDATE works.

# It stores timestamp watermarks as normalized ISO strings and numeric watermarks as normalized integer-like strings.

# reset_checkpoint() intentionally moves the source to full_refresh mode with a null watermark.

# The repository stays persistence-only and does not decide checkpoint timing.

# A matching minimal metadata table would look roughly like this:

# CREATE TABLE checkpoints (
#     namespace VARCHAR(255) NOT NULL,
#     pipeline_name VARCHAR(255) NOT NULL,
#     source_name VARCHAR(255) NOT NULL,
#     checkpoint_strategy VARCHAR(64) NOT NULL,
#     watermark_value TEXT NULL,
#     last_successful_run_id VARCHAR(255) NULL,
#     metadata_json JSON NULL,
#     updated_at DATETIME NOT NULL,
#     PRIMARY KEY (namespace, pipeline_name, source_name)
# );
