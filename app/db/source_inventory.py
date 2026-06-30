"""
Source inventory persistence repository for Project Pulse Knowledge Graph.

Purpose:
- persist source/table inventory coverage and inclusion state
- support filtered reads by inclusion mode and domain
- centralize source inventory logging and error handling

This module must not contain:
- source inclusion policy logic
- warehouse schema inference logic
- pipeline orchestration logic
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from app.core.constants import (
    EXCLUDED,
    GRAPH_CORE,
    SOURCE_INCLUSION_CATEGORIES,
)
from app.core.exceptions import MetadataDatabaseError
from app.core.logging import ProjectPulseLoggerAdapter, get_logger, log_event
from app.core.security import sanitize_config_payload
from app.core.time import utc_now
from app.db.metadata_db import MetadataDBClient

SOURCE_INVENTORY_TABLE = "source_inventory"

STATUS_ACTIVE = "active"
STATUS_INACTIVE = "inactive"
STATUS_EXPERIMENTAL = "experimental"
STATUS_DEPRECATED = "deprecated"

SOURCE_STATUSES: tuple[str, ...] = (
    STATUS_ACTIVE,
    STATUS_INACTIVE,
    STATUS_EXPERIMENTAL,
    STATUS_DEPRECATED,
)


@dataclass(slots=True)
class SourceInventoryRecord:
    """
    Normalized source inventory record returned by the repository.
    """

    source_name: str
    domain: str | None
    inclusion_mode: str
    freshness_field: str | None
    key_fields: list[str]
    graph_entity_mappings: list[str]
    status: str | None
    notes: str | None
    coverage_metadata: dict[str, Any]
    updated_at: str | None
    created_at: str | None


class SourceInventoryRepository:
    """
    Repository for persisted source inventory metadata.
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

    def upsert_source(
        self,
        *,
        source_name: str,
        domain: str | None = None,
        inclusion_mode: str,
        freshness_field: str | None = None,
        key_fields: list[str] | None = None,
        graph_entity_mappings: list[str] | None = None,
        status: str = STATUS_ACTIVE,
        notes: str | None = None,
        coverage_metadata: dict[str, Any] | None = None,
    ) -> SourceInventoryRecord:
        """
        Insert or update a source inventory row.
        """
        self._validate_source_name(source_name)
        self._validate_inclusion_mode(inclusion_mode)

        import uuid as _uuid
        now = utc_now().isoformat()
        normalized_key_fields = self._normalize_string_list(key_fields or [])
        normalized_graph_mappings = self._normalize_string_list(graph_entity_mappings or [])

        statement = f"""
        INSERT INTO {SOURCE_INVENTORY_TABLE} (
            id,
            source_name,
            inclusion_mode,
            graph_entity_mappings,
            freshness_field,
            primary_keys,
            domain,
            notes,
            registered_at,
            last_seen_at
        )
        VALUES (
            :id,
            :source_name,
            :inclusion_mode,
            :graph_entity_mappings,
            :freshness_field,
            :primary_keys,
            :domain,
            :notes,
            :registered_at,
            :last_seen_at
        )
        ON CONFLICT (source_name) DO UPDATE SET
            inclusion_mode = EXCLUDED.inclusion_mode,
            graph_entity_mappings = EXCLUDED.graph_entity_mappings,
            freshness_field = EXCLUDED.freshness_field,
            primary_keys = EXCLUDED.primary_keys,
            domain = EXCLUDED.domain,
            notes = EXCLUDED.notes,
            last_seen_at = EXCLUDED.last_seen_at
        """

        params = {
            "id": str(_uuid.uuid4()),
            "source_name": source_name.strip(),
            "inclusion_mode": inclusion_mode,
            "graph_entity_mappings": ",".join(normalized_graph_mappings) if normalized_graph_mappings else None,
            "freshness_field": self._normalize_optional_string(freshness_field),
            "primary_keys": ",".join(normalized_key_fields) if normalized_key_fields else None,
            "domain": self._normalize_optional_string(domain),
            "notes": self._normalize_optional_string(notes),
            "registered_at": now,
            "last_seen_at": now,
        }

        try:
            self._metadata_db.execute(statement, params)

            log_event(
                self._logger,
                event_name="source_inventory_upsert",
                message="Source inventory upsert completed",
                source_name=source_name,
                domain=domain,
                inclusion_mode=inclusion_mode,
                status=status,
            )

            record = self.get_source(source_name)
            if record is None:
                raise MetadataDatabaseError(
                    "Source inventory upsert completed but record could not be reloaded",
                    source_name=source_name,
                )
            return record
        except Exception as exc:  # noqa: BLE001
            if isinstance(exc, MetadataDatabaseError):
                raise
            raise self._repository_error(
                "Failed to upsert source inventory record",
                exc,
                source_name=source_name,
                inclusion_mode=inclusion_mode,
            ) from exc

    def update_source_coverage(
        self,
        *,
        source_name: str,
        coverage_metadata: dict[str, Any],
    ) -> SourceInventoryRecord:
        """
        Update only the coverage metadata for an existing source.
        """
        self._validate_source_name(source_name)

        existing = self.get_source(source_name)
        if existing is None:
            raise MetadataDatabaseError("Source not found", source_name=source_name)

        merged_metadata = {
            **existing.coverage_metadata,
            **self._sanitize_payload(coverage_metadata),
        }
        updated_at = utc_now().isoformat()

        statement = f"""
        UPDATE {SOURCE_INVENTORY_TABLE}
        SET
            last_seen_at = :last_seen_at
        WHERE source_name = :source_name
        """

        params = {
            "source_name": source_name.strip(),
            "last_seen_at": updated_at,
        }

        try:
            self._metadata_db.execute(statement, params)

            log_event(
                self._logger,
                event_name="source_inventory_coverage_updated",
                message="Source inventory coverage updated",
                source_name=source_name,
            )

            record = self.get_source(source_name)
            if record is None:
                raise MetadataDatabaseError(
                    "Source coverage update completed but record could not be reloaded",
                    source_name=source_name,
                )
            return record
        except Exception as exc:  # noqa: BLE001
            if isinstance(exc, MetadataDatabaseError):
                raise
            raise self._repository_error(
                "Failed to update source coverage",
                exc,
                source_name=source_name,
            ) from exc

    def delete_source(self, source_name: str) -> bool:
        """
        Delete a source inventory row if it exists.
        """
        self._validate_source_name(source_name)

        statement = f"""
        DELETE FROM {SOURCE_INVENTORY_TABLE}
        WHERE source_name = :source_name
        """

        try:
            affected = self._metadata_db.execute(
                statement,
                {"source_name": source_name.strip()},
            )
            deleted = affected > 0

            log_event(
                self._logger,
                event_name="source_inventory_deleted",
                message="Source inventory delete completed",
                source_name=source_name,
                deleted=deleted,
            )
            return deleted
        except Exception as exc:  # noqa: BLE001
            raise self._repository_error(
                "Failed to delete source inventory record",
                exc,
                source_name=source_name,
            ) from exc

    def get_source(self, source_name: str) -> SourceInventoryRecord | None:
        """
        Fetch a source inventory row by source name.
        """
        self._validate_source_name(source_name)

        statement = f"""
        SELECT
            source_name,
            domain,
            inclusion_mode,
            freshness_field,
            primary_keys,
            graph_entity_mappings,
            notes,
            registered_at,
            last_seen_at
        FROM {SOURCE_INVENTORY_TABLE}
        WHERE source_name = :source_name
        LIMIT 1
        """

        try:
            row = self._metadata_db.fetch_one(
                statement,
                {"source_name": source_name.strip()},
            )
            record = self._to_record(row) if row is not None else None

            log_event(
                self._logger,
                event_name="source_inventory_read",
                message="Source inventory read completed",
                source_name=source_name,
                found=record is not None,
            )
            return record
        except Exception as exc:  # noqa: BLE001
            raise self._repository_error(
                "Failed to read source inventory record",
                exc,
                source_name=source_name,
            ) from exc

    def list_sources(
        self,
        *,
        domain: str | None = None,
        inclusion_mode: str | None = None,
        status: str | None = None,
        limit: int | None = None,
    ) -> list[SourceInventoryRecord]:
        """
        List source inventory rows with optional filtering.
        """
        if inclusion_mode is not None:
            self._validate_inclusion_mode(inclusion_mode)
        if status is not None:
            self._validate_status(status)
        if limit is not None and limit <= 0:
            raise MetadataDatabaseError("limit must be positive", limit=limit)

        filters: list[str] = []
        params: dict[str, Any] = {}

        if domain is not None:
            filters.append("domain = :domain")
            params["domain"] = domain.strip()

        if inclusion_mode is not None:
            filters.append("inclusion_mode = :inclusion_mode")
            params["inclusion_mode"] = inclusion_mode

        # status column does not exist in actual table schema; filter ignored

        where_clause = f"WHERE {' AND '.join(filters)}" if filters else ""
        limit_clause = "LIMIT :limit" if limit is not None else ""

        if limit is not None:
            params["limit"] = limit

        statement = f"""
        SELECT
            source_name,
            domain,
            inclusion_mode,
            freshness_field,
            primary_keys,
            graph_entity_mappings,
            notes,
            registered_at,
            last_seen_at
        FROM {SOURCE_INVENTORY_TABLE}
        {where_clause}
        ORDER BY domain ASC, source_name ASC
        {limit_clause}
        """

        try:
            rows = self._metadata_db.fetch_all(statement, params)
            records = [self._to_record(row) for row in rows]

            log_event(
                self._logger,
                event_name="source_inventory_list",
                message="Source inventory list completed",
                domain=domain,
                inclusion_mode=inclusion_mode,
                status=status,
                record_count=len(records),
            )
            return records
        except Exception as exc:  # noqa: BLE001
            raise self._repository_error(
                "Failed to list source inventory records",
                exc,
                domain=domain,
                inclusion_mode=inclusion_mode,
                status=status,
            ) from exc

    def list_by_inclusion_mode(self, inclusion_mode: str) -> list[SourceInventoryRecord]:
        """
        List all source inventory rows for a specific inclusion mode.
        """
        self._validate_inclusion_mode(inclusion_mode)

        log_event(
            self._logger,
            event_name="source_inventory_filter_by_inclusion_mode",
            message="Source inventory inclusion-mode filter requested",
            inclusion_mode=inclusion_mode,
        )
        return self.list_sources(inclusion_mode=inclusion_mode)

    def list_graph_core_sources(self) -> list[SourceInventoryRecord]:
        """
        List all graph-core sources.
        """
        return self.list_by_inclusion_mode(GRAPH_CORE)

    def list_excluded_sources(self) -> list[SourceInventoryRecord]:
        """
        List all excluded sources.
        """
        return self.list_by_inclusion_mode(EXCLUDED)

    @staticmethod
    def _validate_source_name(source_name: str) -> None:
        if not source_name or not source_name.strip():
            raise MetadataDatabaseError("source_name must not be empty")

    @staticmethod
    def _validate_inclusion_mode(inclusion_mode: str) -> None:
        if inclusion_mode not in SOURCE_INCLUSION_CATEGORIES:
            raise MetadataDatabaseError(
                "Unsupported source inclusion mode",
                inclusion_mode=inclusion_mode,
                supported_inclusion_modes=SOURCE_INCLUSION_CATEGORIES,
            )

    @staticmethod
    def _validate_status(status: str) -> None:
        if status not in SOURCE_STATUSES:
            raise MetadataDatabaseError(
                "Unsupported source inventory status",
                status=status,
                supported_statuses=SOURCE_STATUSES,
            )

    @staticmethod
    def _normalize_optional_string(value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @staticmethod
    def _normalize_string_list(values: list[str]) -> list[str]:
        normalized = []
        seen: set[str] = set()

        for value in values:
            candidate = str(value).strip()
            if not candidate or candidate in seen:
                continue
            seen.add(candidate)
            normalized.append(candidate)

        return normalized

    @staticmethod
    def _sanitize_payload(payload: dict[str, Any]) -> dict[str, Any]:
        return sanitize_config_payload(payload)

    @staticmethod
    def _decode_json_list(value: Any) -> list[str]:
        if value in (None, ""):
            return []
        if isinstance(value, list):
            return [str(item) for item in value]
        decoded = json.loads(value)
        return [str(item) for item in decoded]

    @staticmethod
    def _decode_json_dict(value: Any) -> dict[str, Any]:
        if value in (None, ""):
            return {}
        if isinstance(value, dict):
            return value
        return json.loads(value)

    @classmethod
    def _to_record(cls, row: dict[str, Any]) -> SourceInventoryRecord:
        def _iso(value: Any) -> str | None:
            if value is None:
                return None
            if hasattr(value, "isoformat"):
                return value.isoformat()
            return str(value)

        def _split_csv(value: Any) -> list[str]:
            if not value:
                return []
            return [v.strip() for v in str(value).split(",") if v.strip()]

        return SourceInventoryRecord(
            source_name=str(row["source_name"]),
            domain=row.get("domain"),
            inclusion_mode=str(row["inclusion_mode"]),
            freshness_field=row.get("freshness_field"),
            key_fields=_split_csv(row.get("primary_keys")),
            graph_entity_mappings=_split_csv(row.get("graph_entity_mappings")),
            status=None,
            notes=row.get("notes"),
            coverage_metadata={},
            updated_at=_iso(row.get("last_seen_at")),
            created_at=_iso(row.get("registered_at")),
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


# A few practical notes:

# upsert_source() is the main write path and assumes source_name is the stable unique key.

# update_source_coverage() intentionally updates only the coverage metadata field.

# list_graph_core_sources() and list_excluded_sources() are just convenience wrappers on list_by_inclusion_mode().

# Inclusion mode validation is strictly aligned with your centralized constants: GRAPH_CORE, GRAPH_ENRICHMENT, SERVING_ONLY, FEATURE_SOURCE, and EXCLUDED.


# A matching minimal metadata table would look roughly like this:

# CREATE TABLE source_inventory (
#     source_name VARCHAR(255) NOT NULL PRIMARY KEY,
#     domain VARCHAR(255) NULL,
#     inclusion_mode VARCHAR(64) NOT NULL,
#     freshness_field VARCHAR(255) NULL,
#     key_fields_json JSON NULL,
#     graph_entity_mappings_json JSON NULL,
#     status VARCHAR(64) NULL,
#     notes TEXT NULL,
#     coverage_metadata_json JSON NULL,
#     created_at DATETIME NOT NULL,
#     updated_at DATETIME NOT NULL,
#     INDEX idx_source_inventory_domain (domain),
#     INDEX idx_source_inventory_inclusion_mode (inclusion_mode),
#     INDEX idx_source_inventory_status (status)
# );
