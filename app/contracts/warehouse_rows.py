"""
Typed contract layer for warehouse row payloads.

This module defines the shared abstractions that allow pipeline and orchestration
layers to move extractor output between stages without coupling to individual
schema files.

Design rules:
- Do not import any individual schema file from app/schemas/warehouse/.
- All extractors must return ExtractorBatch.
- All pipelines must accept ExtractorBatch without knowing the concrete row type.
- Factory helpers are the only permitted way to construct ExtractorBatch and
  ExtractionManifest instances outside of tests.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from app.core.constants import (
    GRAPH_CORE,
    SOURCE_INCLUSION_CATEGORIES,
)
from app.core.exceptions import ValidationError
from app.core.time import format_iso_timestamp, utc_now


# WarehouseRow protocol

@runtime_checkable
class WarehouseRow(Protocol):
    """
    Structural protocol that every warehouse *Row dataclass implicitly satisfies.

    Any dataclass that implements a `from_row` classmethod accepting a raw dict
    and returning an instance of itself conforms to this protocol.

    Extractor return types are not imported here — conformance is structural.
    """

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "WarehouseRow":
        """
        Construct a typed row instance from a raw warehouse result dict.

        Args:
            row: Raw dict as returned by a warehouse query cursor.

        Returns:
            A typed *Row instance.
        """
        ...


# ExtractorBatch

@dataclass(frozen=True)
class ExtractorBatch:
    """
    Typed container for a single batch of warehouse rows returned by an extractor.

    Attributes:
        source_name:      Logical source/table name (e.g. "dim_users").
        inclusion_mode:   Source inclusion category from constants.SOURCE_INCLUSION_CATEGORIES.
        rows:             List of typed *Row instances. Never raw dicts.
        row_count:        Number of rows in this batch. Must equal len(rows).
        watermark_value:  Watermark high-water mark for this batch, ISO timestamp or None.
        extracted_at:     ISO UTC timestamp when extraction completed.
        pipeline_run_id:  Run ID of the owning pipeline execution.
        batch_id:         Unique identifier for this specific batch within the run.
    """

    source_name: str
    inclusion_mode: str
    rows: list[Any]
    row_count: int
    watermark_value: str | None
    extracted_at: str
    pipeline_run_id: str
    batch_id: str

    def __post_init__(self) -> None:
        _validate_extractor_batch(self)

    def is_empty(self) -> bool:
        """Return True if this batch contains no rows."""
        return self.row_count == 0

    def has_watermark(self) -> bool:
        """Return True if a watermark value is present."""
        return self.watermark_value is not None and bool(self.watermark_value.strip())


# ExtractionManifest

@dataclass(frozen=True)
class ExtractionManifest:
    """
    Summary record for a completed extraction operation.

    Created after all batches for a source have been extracted. Used by the
    pipeline layer to record run metadata and update checkpoint state.

    Attributes:
        pipeline_run_id:  Run ID of the owning pipeline execution.
        source_name:      Logical source/table name.
        total_rows:       Total rows extracted across all batches.
        batch_count:      Total number of batches emitted.
        watermark_before: Watermark at start of extraction (prior run high-water mark).
        watermark_after:  Watermark at end of extraction (new high-water mark).
        started_at:       ISO UTC timestamp when extraction started.
        finished_at:      ISO UTC timestamp when extraction completed.
        status:           One of "success", "partial", "failed".
        error_message:    Error detail if status is "partial" or "failed", else None.
    """

    pipeline_run_id: str
    source_name: str
    total_rows: int
    batch_count: int
    watermark_before: str | None
    watermark_after: str | None
    started_at: str
    finished_at: str
    status: str
    error_message: str | None

    _VALID_STATUSES: frozenset[str] = field(
        default=frozenset({"success", "partial", "failed"}),
        init=False,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        _validate_extraction_manifest(self)

    def is_successful(self) -> bool:
        """Return True if the extraction completed without error."""
        return self.status == "success"

    def is_failed(self) -> bool:
        """Return True if the extraction failed entirely."""
        return self.status == "failed"

    def is_partial(self) -> bool:
        """Return True if extraction completed with partial data."""
        return self.status == "partial"

    def watermark_advanced(self) -> bool:
        """
        Return True if the watermark moved forward during this extraction.

        Returns False when either watermark is absent or they are equal.
        """
        if self.watermark_before is None or self.watermark_after is None:
            return self.watermark_after is not None
        return self.watermark_after != self.watermark_before


# Internal validators


def _validate_extractor_batch(batch: ExtractorBatch) -> None:
    """
    Validate an ExtractorBatch on construction.

    Raises:
        ValidationError: If any field is invalid.
    """
    if not batch.source_name or not batch.source_name.strip():
        raise ValidationError(
            "ExtractorBatch.source_name cannot be empty",
            field="source_name",
        )

    if batch.inclusion_mode not in SOURCE_INCLUSION_CATEGORIES:
        raise ValidationError(
            "ExtractorBatch.inclusion_mode is not a recognised inclusion category",
            field="inclusion_mode",
            value=batch.inclusion_mode,
            valid_values=SOURCE_INCLUSION_CATEGORIES,
        )

    if batch.row_count < 0:
        raise ValidationError(
            "ExtractorBatch.row_count cannot be negative",
            field="row_count",
            value=batch.row_count,
        )

    if len(batch.rows) != batch.row_count:
        raise ValidationError(
            "ExtractorBatch.row_count must equal len(rows)",
            field="row_count",
            declared=batch.row_count,
            actual=len(batch.rows),
        )

    if not batch.pipeline_run_id or not batch.pipeline_run_id.strip():
        raise ValidationError(
            "ExtractorBatch.pipeline_run_id cannot be empty",
            field="pipeline_run_id",
        )

    if not batch.batch_id or not batch.batch_id.strip():
        raise ValidationError(
            "ExtractorBatch.batch_id cannot be empty",
            field="batch_id",
        )

    if not batch.extracted_at or not batch.extracted_at.strip():
        raise ValidationError(
            "ExtractorBatch.extracted_at cannot be empty",
            field="extracted_at",
        )


def _validate_extraction_manifest(manifest: ExtractionManifest) -> None:
    """
    Validate an ExtractionManifest on construction.

    Raises:
        ValidationError: If any field is invalid.
    """
    valid_statuses = {"success", "partial", "failed"}

    if not manifest.pipeline_run_id or not manifest.pipeline_run_id.strip():
        raise ValidationError(
            "ExtractionManifest.pipeline_run_id cannot be empty",
            field="pipeline_run_id",
        )

    if not manifest.source_name or not manifest.source_name.strip():
        raise ValidationError(
            "ExtractionManifest.source_name cannot be empty",
            field="source_name",
        )

    if manifest.total_rows < 0:
        raise ValidationError(
            "ExtractionManifest.total_rows cannot be negative",
            field="total_rows",
            value=manifest.total_rows,
        )

    if manifest.batch_count < 0:
        raise ValidationError(
            "ExtractionManifest.batch_count cannot be negative",
            field="batch_count",
            value=manifest.batch_count,
        )

    if manifest.status not in valid_statuses:
        raise ValidationError(
            "ExtractionManifest.status must be one of: success, partial, failed",
            field="status",
            value=manifest.status,
        )

    if manifest.status in {"partial", "failed"} and not manifest.error_message:
        raise ValidationError(
            "ExtractionManifest.error_message is required when status is partial or failed",
            field="error_message",
            status=manifest.status,
        )

    if not manifest.started_at or not manifest.started_at.strip():
        raise ValidationError(
            "ExtractionManifest.started_at cannot be empty",
            field="started_at",
        )

    if not manifest.finished_at or not manifest.finished_at.strip():
        raise ValidationError(
            "ExtractionManifest.finished_at cannot be empty",
            field="finished_at",
        )


# Factory helpers

def _generate_batch_id() -> str:
    """Generate a unique batch ID."""
    return f"batch-{uuid.uuid4().hex[:16]}"


def build_extractor_batch(
    source_name: str,
    rows: list[Any],
    *,
    run_id: str,
    watermark: str | None = None,
    inclusion_mode: str = GRAPH_CORE,
    batch_id: str | None = None,
    extracted_at: str | None = None,
) -> ExtractorBatch:
    """
    Construct an ExtractorBatch for a completed extraction pass.

    Args:
        source_name:    Logical source/table name.
        rows:           List of typed *Row instances.
        run_id:         Pipeline run ID.
        watermark:      High-water mark timestamp for this batch, or None.
        inclusion_mode: Source inclusion category. Defaults to GRAPH_CORE.
        batch_id:       Optional explicit batch ID. Auto-generated if omitted.
        extracted_at:   Optional ISO timestamp. Defaults to utc_now().

    Returns:
        Validated ExtractorBatch.

    Raises:
        ValidationError: If any required field is missing or invalid.
    """
    return ExtractorBatch(
        source_name=source_name,
        inclusion_mode=inclusion_mode,
        rows=rows,
        row_count=len(rows),
        watermark_value=watermark,
        extracted_at=extracted_at or format_iso_timestamp(utc_now()),
        pipeline_run_id=run_id,
        batch_id=batch_id or _generate_batch_id(),
    )


def build_extraction_manifest(
    *,
    run_id: str,
    source_name: str,
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
    Construct an ExtractionManifest summarising a completed extraction.

    Args:
        run_id:            Pipeline run ID.
        source_name:       Logical source/table name.
        total_rows:        Total rows extracted across all batches.
        batch_count:       Total number of batches emitted.
        watermark_before:  Watermark at start of extraction.
        watermark_after:   New watermark high-water mark.
        started_at:        ISO UTC timestamp when extraction started.
        finished_at:       ISO UTC timestamp when extraction completed.
        status:            "success", "partial", or "failed".
        error_message:     Error detail for non-success statuses.

    Returns:
        Validated ExtractionManifest.

    Raises:
        ValidationError: If any required field is missing or invalid.
    """
    return ExtractionManifest(
        pipeline_run_id=run_id,
        source_name=source_name,
        total_rows=total_rows,
        batch_count=batch_count,
        watermark_before=watermark_before,
        watermark_after=watermark_after,
        started_at=started_at,
        finished_at=finished_at,
        status=status,
        error_message=error_message,
    )


def build_failed_extraction_manifest(
    *,
    run_id: str,
    source_name: str,
    started_at: str,
    error_message: str,
    total_rows: int = 0,
    batch_count: int = 0,
    watermark_before: str | None = None,
) -> ExtractionManifest:
    """
    Convenience constructor for a fully failed extraction.

    Args:
        run_id:           Pipeline run ID.
        source_name:      Logical source/table name.
        started_at:       ISO UTC timestamp when extraction started.
        error_message:    Required error description.
        total_rows:       Rows extracted before failure. Defaults to 0.
        batch_count:      Batches emitted before failure. Defaults to 0.
        watermark_before: Pre-extraction watermark, if known.

    Returns:
        ExtractionManifest with status="failed".
    """
    return build_extraction_manifest(
        run_id=run_id,
        source_name=source_name,
        total_rows=total_rows,
        batch_count=batch_count,
        watermark_before=watermark_before,
        watermark_after=None,
        started_at=started_at,
        finished_at=format_iso_timestamp(utc_now()),
        status="failed",
        error_message=error_message,
    )


# Batch aggregation helpers

def merge_batches(batches: list[ExtractorBatch]) -> list[Any]:
    """
    Flatten a list of ExtractorBatch objects into a single row list.

    Useful when a pipeline stage needs to process all rows from multiple
    batches as one collection.

    Args:
        batches: List of ExtractorBatch instances from the same source.

    Returns:
        Flat list of all typed row instances.
    """
    result: list[Any] = []
    for batch in batches:
        result.extend(batch.rows)
    return result


def total_row_count(batches: list[ExtractorBatch]) -> int:
    """
    Sum the row counts across a list of ExtractorBatch objects.

    Args:
        batches: List of ExtractorBatch instances.

    Returns:
        Total row count.
    """
    return sum(batch.row_count for batch in batches)


def latest_watermark(batches: list[ExtractorBatch]) -> str | None:
    """
    Return the latest non-null watermark value across a list of batches.

    Comparison is lexicographic — works correctly for ISO timestamp strings.

    Args:
        batches: List of ExtractorBatch instances.

    Returns:
        Latest watermark string, or None if all batches have no watermark.
    """
    candidates = [
        batch.watermark_value
        for batch in batches
        if batch.watermark_value is not None and batch.watermark_value.strip()
    ]

    if not candidates:
        return None

    return max(candidates)