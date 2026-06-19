"""
Shared runtime foundation for warehouse extractors.

This module defines the common extraction runtime used by every concrete
extractor in app/extractors/*.

It standardizes:

- query construction and execution via MySQLClient
- incremental watermark filtering
- deterministic ordering
- chunked / paginated extraction
- typed warehouse row coercion
- ExtractorBatch construction
- ExtractionManifest construction
- structured logging hooks
- validation and error wrapping

Design rules:
- This module knows only warehouse extraction concerns. It must not contain
  graph logic, canonicalization, mapping behavior, or loader concerns.
- Concrete extractors define source-specific SQL, source columns, ordering,
  and watermark behavior by overriding abstract methods.
- All extractor outputs must be typed warehouse rows wrapped in
  ExtractorBatch, never raw dicts.
- Full-refresh/static sources and incremental sources must both be supported
  through one uniform runtime API.

Primary guarantees:
- source registration is validated
- row coercion is validated
- incremental configuration is validated
- batch metadata is always populated
- extraction manifests are built consistently

This file exists so all domain extractors can inherit one stable runtime
contract rather than reimplementing warehouse access and batching logic.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable, Protocol, cast
import math
import uuid

from app.contracts.warehouse_rows import (
    ExtractionManifest,
    ExtractorBatch,
    WarehouseRow,
    build_extraction_manifest,
    build_extractor_batch,
)

from app.core.config import get_settings
from app.core.exceptions import ConfigurationError, ExtractorError
from app.core.logging import get_logger, log_event
from app.core.time import format_log_timestamp, warehouse_value_to_utc_datetime
from app.db.mysql_client import MySQLClient
from app.mappings.source_to_graph import get_source_artifacts
from app.source_inventory import registry as source_registry

LOGGER = get_logger(__name__)


class SupportsFromRow(Protocol):
    """
    Minimal protocol required from warehouse row dataclasses.
    """

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> WarehouseRow:
        ...


@dataclass(frozen=True)
class ExtractionWindow:
    """
    Optional extraction window information used to build incremental clauses.

    Attributes:
        watermark_value:
            The last processed watermark from checkpoints, if any.
        lower_bound_inclusive:
            Optional explicit lower-bound override.
        upper_bound_exclusive:
            Optional explicit upper-bound override.
    """

    watermark_value: str | None
    lower_bound_inclusive: str | None = None
    upper_bound_exclusive: str | None = None


class BaseExtractor(ABC):
    """
    Shared base class for all warehouse extractors.

    Responsibilities:
    - execute source SQL through MySQLClient
    - apply incremental watermark filters when configured
    - paginate / chunk large result sets
    - convert raw rows into typed warehouse row dataclasses
    - build ExtractorBatch and ExtractionManifest outputs
    """

    source_name: str = ""
    schema_row_class: type[WarehouseRow] | None = None
    inclusion_mode: str = ""
    freshness_field: str | None = None
    primary_key_fields: tuple[str, ...] = ()
    default_chunk_size: int = 1000
    supports_incremental: bool = False

    def __init__(
        self,
        mysql_client: MySQLClient,
        *,
        chunk_size: int | None = None,
    ) -> None:
        self.mysql_client = mysql_client
        self.settings = get_settings()
        self.chunk_size = chunk_size or self.default_chunk_size
        self._validate_configuration()

    
    # Required extractor API
    

    @abstractmethod
    def build_base_query(self) -> str:
        """
        Return the source SELECT statement without incremental filter clauses.
        """

    @abstractmethod
    def get_source_columns(self) -> tuple[str, ...]:
        """
        Return the explicit ordered source columns used by the query.
        """

    def build_incremental_clause(self, watermark_value: str | None) -> str:
        """
        Return the incremental WHERE/AND clause if supports_incremental is True.

        Default behavior:
        - no clause for non-incremental sources
        - `freshness_field > watermark_value` for incremental sources when a
          watermark is supplied
        """
        if not self.supports_incremental or not self.freshness_field:
            return ""

        if not watermark_value:
            return ""

        return f" WHERE {self.freshness_field} > %(watermark_value)s"

    def build_order_by_clause(self) -> str:
        """
        Return the stable ORDER BY for deterministic extraction.

        Default behavior:
        - freshness field first if available
        - then declared primary key fields
        """
        order_fields: list[str] = []

        if self.freshness_field:
            order_fields.append(self.freshness_field)

        order_fields.extend(self.primary_key_fields)

        if not order_fields:
            raise ConfigurationError(
                "Extractor must declare freshness_field or primary_key_fields to build ORDER BY",
                source_name=self.source_name,
            )

        return " ORDER BY " + ", ".join(order_fields)

    def build_pagination_clause(self, limit: int, offset: int) -> str:
        """
        Return LIMIT/OFFSET clause for chunked extraction.
        """
        return " LIMIT %(limit)s OFFSET %(offset)s"

    
    # Public extraction API
    

    def extract_all(
        self,
        run_id: str,
        watermark_value: str | None = None,
    ) -> ExtractorBatch:
        """
        Extract all rows for the source in a single batch.

        This is typically appropriate for:
        - low-volume sources
        - static/full refresh dimensions
        - tests and local workflows
        """
        started_at = format_log_timestamp()
        try:
            raw_rows = self._fetch_raw_rows(
                watermark_value=watermark_value,
                limit=None,
                offset=None,
            )
            rows = self._coerce_rows(raw_rows)
            watermark_after = self._compute_watermark_after(rows, watermark_value)

            batch = build_extractor_batch(
                self.source_name,
                rows,
                run_id=run_id,
                watermark=watermark_after,
                inclusion_mode=self.inclusion_mode,
            )

            log_event(
                LOGGER,
                "extractor.extract_all.success",
                source_name=self.source_name,
                row_count=batch.row_count,
                watermark_before=watermark_value,
                watermark_after=watermark_after,
                pipeline_run_id=run_id,
            )
            return batch
        except Exception as exc:
            self._raise_extraction_error(
                "extract_all failed",
                exc,
                run_id=run_id,
                watermark_value=watermark_value,
                started_at=started_at,
            )

    def extract_in_chunks(
        self,
        run_id: str,
        watermark_value: str | None = None,
    ) -> list[ExtractorBatch]:
        """
        Extract rows in deterministic paginated chunks.

        This is typically appropriate for:
        - large fact tables
        - incremental event sources
        - high-volume telemetry sources
        """
        started_at = format_log_timestamp()
        batches: list[ExtractorBatch] = []
        offset = 0
        batch_seq = 0
        watermark_after: str | None = watermark_value

        try:
            while True:
                raw_rows = self._fetch_raw_rows(
                    watermark_value=watermark_value,
                    limit=self.chunk_size,
                    offset=offset,
                )
                if not raw_rows:
                    break

                rows = self._coerce_rows(raw_rows)
                watermark_after = self._compute_watermark_after(rows, watermark_after)

                batch = self._build_chunk_batch(
                    rows=rows,
                    run_id=run_id,
                    watermark_value=watermark_after,
                    batch_sequence=batch_seq,
                )
                batches.append(batch)

                log_event(
                    LOGGER,
                    "extractor.extract_chunk.success",
                    source_name=self.source_name,
                    row_count=batch.row_count,
                    batch_sequence=batch_seq,
                    offset=offset,
                    chunk_size=self.chunk_size,
                    watermark_before=watermark_value,
                    watermark_after=watermark_after,
                    pipeline_run_id=run_id,
                )

                if len(raw_rows) < self.chunk_size:
                    break

                offset += self.chunk_size
                batch_seq += 1

            return batches
        except Exception as exc:
            self._raise_extraction_error(
                "extract_in_chunks failed",
                exc,
                run_id=run_id,
                watermark_value=watermark_value,
                started_at=started_at,
            )

    def extract_manifest(
        self,
        *,
        run_id: str,
        total_rows: int,
        batch_count: int,
        watermark_before: str | None,
        watermark_after: str | None,
        started_at: str,
        finished_at: str,
        status: str = "success",
        error_message: str | None = None,
    ) -> ExtractionManifest:
        """
        Build a manifest summarizing an extraction run for this source.
        """
        return build_extraction_manifest(
            pipeline_run_id=run_id,
            source_name=self.source_name,
            total_rows=total_rows,
            batch_count=batch_count,
            watermark_before=watermark_before,
            watermark_after=watermark_after,
            started_at=started_at,
            finished_at=finished_at,
            status=status,
            error_message=error_message,
        )

    
    # Shared runtime helpers
    

    def _fetch_raw_rows(
        self,
        *,
        watermark_value: str | None,
        limit: int | None,
        offset: int | None,
    ) -> list[dict[str, Any]]:
        """
        Execute the source query and return raw result dicts.
        """
        query = self._build_query(
            watermark_value=watermark_value,
            limit=limit,
            offset=offset,
        )
        params = self._build_query_params(
            watermark_value=watermark_value,
            limit=limit,
            offset=offset,
        )

        log_event(
            LOGGER,
            "extractor.fetch_raw_rows.start",
            source_name=self.source_name,
            supports_incremental=self.supports_incremental,
            freshness_field=self.freshness_field,
            has_watermark=watermark_value is not None,
            limit=limit,
            offset=offset,
        )

        rows = self.mysql_client.fetch_all(query, params=params)
        if not isinstance(rows, list):
            raise ExtractorError(
                "MySQL client returned unexpected result type",
                source_name=self.source_name,
                result_type=type(rows).__name__,
            )

        return [dict(row) for row in rows]

    def _coerce_rows(self, raw_rows: list[dict[str, Any]]) -> list[WarehouseRow]:
        """
        Convert raw dict rows into typed warehouse row instances.
        """
        row_class = self._get_schema_row_class()
        coerced: list[WarehouseRow] = []

        for index, raw_row in enumerate(raw_rows):
            try:
                typed_row = cast(SupportsFromRow, row_class).from_row(raw_row)
            except Exception as exc:
                raise ExtractorError(
                    "Failed to coerce raw row into typed warehouse row",
                    source_name=self.source_name,
                    row_index=index,
                    row_class=row_class.__name__,
                    raw_row=raw_row,
                    error=str(exc),
                ) from exc

            if isinstance(typed_row, dict):
                raise ExtractorError(
                    "Extractor row coercion returned a raw dict instead of a typed row",
                    source_name=self.source_name,
                    row_index=index,
                    row_class=row_class.__name__,
                )

            coerced.append(typed_row)

        return coerced

    def _compute_watermark_after(
        self,
        rows: Iterable[WarehouseRow],
        watermark_before: str | None,
    ) -> str | None:
        """
        Compute watermark_after from extracted typed rows.

        Supported modes:
        - full refresh / static -> returns input watermark unchanged
        - incremental timestamp -> returns max ISO UTC timestamp
        - incremental numeric -> returns max numeric value as string
        """
        if not self.supports_incremental or not self.freshness_field:
            return watermark_before

        values: list[Any] = []
        for row in rows:
            value = getattr(row, self.freshness_field, None)
            if value is not None:
                values.append(value)

        if not values:
            return watermark_before

        # Try datetime semantics first.
        normalized_datetimes: list[datetime] = []
        datetime_failed = False
        for value in values:
            try:
                dt = warehouse_value_to_utc_datetime(value)
                if dt is None:
                    datetime_failed = True
                    break
                normalized_datetimes.append(dt)
            except Exception:
                datetime_failed = True
                break

        if not datetime_failed and normalized_datetimes:
            return max(normalized_datetimes).isoformat()

        # Fall back to numeric semantics.
        numeric_values: list[float] = []
        numeric_failed = False
        for value in values:
            try:
                numeric_values.append(float(value))
            except Exception:
                numeric_failed = True
                break

        if not numeric_failed and numeric_values:
            max_value = max(numeric_values)
            if math.isfinite(max_value):
                if max_value.is_integer():
                    return str(int(max_value))
                return str(max_value)

        # Final fallback: lexical max.
        string_values = [str(value) for value in values if value is not None]
        return max(string_values) if string_values else watermark_before

    
    # Validation / configuration
    

    def _validate_configuration(self) -> None:
        """
        Validate extractor configuration and guardrails.
        """
        if not self.source_name or not self.source_name.strip():
            raise ConfigurationError("Extractor source_name cannot be empty")

        if not self.inclusion_mode or not self.inclusion_mode.strip():
            raise ConfigurationError(
                "Extractor inclusion_mode cannot be empty",
                source_name=self.source_name,
            )

        self._get_schema_row_class()

        if self.default_chunk_size <= 0 and self.chunk_size <= 0:
            raise ConfigurationError(
                "Extractor chunk size must be positive",
                source_name=self.source_name,
                chunk_size=self.chunk_size,
            )

        if self.supports_incremental and not self.freshness_field:
            raise ConfigurationError(
                "Incremental extractor must declare freshness_field",
                source_name=self.source_name,
            )

        if not self.primary_key_fields and not self.freshness_field:
            raise ConfigurationError(
                "Extractor must declare primary_key_fields or freshness_field for deterministic ordering",
                source_name=self.source_name,
            )

        self._validate_source_registration()

    def _validate_source_registration(self) -> None:
        """
        Best-effort validation that the source is known to the source inventory
        and mapping layers.
        """
        registered_source_names = self._get_registered_source_names()
        if registered_source_names is not None and self.source_name not in registered_source_names:
            raise ConfigurationError(
                "Extractor source_name is not registered in source inventory",
                source_name=self.source_name,
            )

        # Ensure mapping/routing layer also knows the source, even if it is
        # non-graph-emitting.
        try:
            get_source_artifacts(self.source_name)
        except Exception:
            # Do not fail here if routing layer has no declaration yet; source
            # inventory remains the stronger extraction-time requirement.
            pass

    def _get_schema_row_class(self) -> type[WarehouseRow]:
        """
        Validate and return the declared schema row class.
        """
        if self.schema_row_class is None:
            raise ConfigurationError(
                "Extractor must declare schema_row_class",
                source_name=self.source_name,
            )

        if not hasattr(self.schema_row_class, "from_row"):
            raise ConfigurationError(
                "schema_row_class must define from_row()",
                source_name=self.source_name,
                row_class=getattr(self.schema_row_class, "__name__", str(self.schema_row_class)),
            )

        return self.schema_row_class

    
    # Query assembly helpers
    

    def _build_query(
        self,
        *,
        watermark_value: str | None,
        limit: int | None,
        offset: int | None,
    ) -> str:
        """
        Build the final executable SQL query.
        """
        query = self.build_base_query().rstrip()
        if not query:
            raise ConfigurationError(
                "build_base_query() returned empty SQL",
                source_name=self.source_name,
            )

        incremental_clause = self.build_incremental_clause(watermark_value).rstrip()
        order_clause = self.build_order_by_clause().rstrip()

        if incremental_clause:
            query += incremental_clause
        if order_clause:
            query += order_clause
        if limit is not None:
            query += self.build_pagination_clause(limit, offset or 0).rstrip()

        return query

    def _build_query_params(
        self,
        *,
        watermark_value: str | None,
        limit: int | None,
        offset: int | None,
    ) -> dict[str, Any]:
        """
        Build the parameter dict for the final query.
        """
        params: dict[str, Any] = {}
        if watermark_value is not None:
            params["watermark_value"] = watermark_value
        if limit is not None:
            params["limit"] = limit
            params["offset"] = offset or 0
        return params

    def _build_chunk_batch(
        self,
        *,
        rows: list[WarehouseRow],
        run_id: str,
        watermark_value: str | None,
        batch_sequence: int,
    ) -> ExtractorBatch:
        """
        Build a chunk-scoped ExtractorBatch with stable per-batch metadata.
        """
        batch = build_extractor_batch(
            self.source_name,
            rows,
            run_id=run_id,
            watermark=watermark_value,
            inclusion_mode=self.inclusion_mode,
        )

        # If your build_extractor_batch already sets a batch_id, this preserves
        # the contract while replacing it with a deterministic chunk-specific id.
        return ExtractorBatch(
            source_name=batch.source_name,
            inclusion_mode=batch.inclusion_mode,
            rows=batch.rows,
            row_count=batch.row_count,
            watermark_value=batch.watermark_value,
            extracted_at=batch.extracted_at,
            pipeline_run_id=batch.pipeline_run_id,
            batch_id=self._make_batch_id(run_id, batch_sequence),
        )

    def _make_batch_id(self, run_id: str, batch_sequence: int) -> str:
        """
        Build a unique, traceable batch id for extractor output.
        """
        return f"{self.source_name}:{run_id}:{batch_sequence}:{uuid.uuid4().hex[:8]}"

    def _raise_extraction_error(
        self,
        message: str,
        exc: Exception,
        *,
        run_id: str,
        watermark_value: str | None,
        started_at: str,
    ) -> None:
        """
        Wrap and raise extraction failures consistently.
        """
        finished_at = format_log_timestamp()

        log_event(
            LOGGER,
            "extractor.failure",
            source_name=self.source_name,
            pipeline_run_id=run_id,
            watermark_before=watermark_value,
            started_at=started_at,
            finished_at=finished_at,
            error=str(exc),
        )

        raise ExtractorError(
            message,
            source_name=self.source_name,
            pipeline_run_id=run_id,
            watermark_before=watermark_value,
            error=str(exc),
        ) from exc

    
    # Best-effort source inventory introspection
    

    def _get_registered_source_names(self) -> set[str] | None:
        """
        Best-effort introspection of source inventory registry source names.
        """
        candidate_names = (
            "SOURCE_REGISTRY",
            "SOURCE_REGISTRATIONS",
            "SOURCE_DEFINITIONS",
            "REGISTERED_SOURCES",
            "ALL_SOURCES",
        )

        for attribute_name in candidate_names:
            if not hasattr(source_registry, attribute_name):
                continue

            value = getattr(source_registry, attribute_name)
            names = self._extract_source_names(value)
            if names:
                return names

        return None

    def _extract_source_names(self, value: Any) -> set[str]:
        """
        Extract source names from a registry-like object.
        """
        if isinstance(value, dict):
            names = {str(key).strip() for key in value.keys() if str(key).strip()}
            if names:
                return names

            extracted: set[str] = set()
            for item in value.values():
                name = self._source_name_from_item(item)
                if name:
                    extracted.add(name)
            return extracted

        if isinstance(value, (list, tuple, set, frozenset)):
            extracted: set[str] = set()
            for item in value:
                name = self._source_name_from_item(item)
                if name:
                    extracted.add(name)
            return extracted

        return set()

    def _source_name_from_item(self, item: Any) -> str | None:
        """
        Best-effort extraction of source_name from one registry item.
        """
        if isinstance(item, str):
            stripped = item.strip()
            return stripped or None

        if isinstance(item, dict):
            raw = item.get("source_name")
            if raw is None:
                return None
            stripped = str(raw).strip()
            return stripped or None

        raw = getattr(item, "source_name", None)
        if raw is None:
            return None

        stripped = str(raw).strip()
        return stripped or None