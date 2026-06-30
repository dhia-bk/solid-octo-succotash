"""
app/transformers/base.py
========================
Shared transformer runtime.

Every domain transformer inherits from BaseTransformer. This module solves
the common mechanics once:

- typed input contract (ExtractorBatch)
- typed output contract (GraphWriteBatch)
- type coercion helpers (_ts, _bool, _int)
- lifecycle logging (started / finished / validation failure)
- per-row skip tracking
- canonicalizer registry access
- endpoint resolution via declared EndpointSpec

Design rules:
- This file must not import any DB client, loader, pipeline module, or
  schema row class.
- No domain-specific logic belongs here.
- Every method on BaseTransformer is either abstract or a shared utility
  that every domain transformer would otherwise duplicate.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from app.canonicalization.base import BaseCanonicalizer, CanonicalForm
from app.contracts.graph_records import GraphWriteBatch
from app.contracts.warehouse_rows import ExtractorBatch
from app.core.exceptions import CanonicalizationError, TransformationError
from app.core.ids import normalize_string_id
from app.core.logging import (
    ProjectPulseLoggerAdapter,
    get_logger,
    log_transformation_finished,
    log_transformation_started,
    log_validation_failure,
)
from app.core.time import format_iso_timestamp
from app.mappings.endpoint_resolution import get_endpoint_spec
from app.mappings.registry import MappingRegistry


class BaseTransformer(ABC):
    """
    Abstract base class for all warehouse → graph transformers.

    Responsibilities:
    - enforce typed input/output contract
    - provide shared coercion helpers
    - provide lifecycle logging helpers
    - provide canonicalizer registry access
    - provide endpoint resolution via declared EndpointSpec

    Subclass requirements:
    - declare class attributes `source_name` and `inclusion_mode` matching
      the corresponding schema module constants
    - implement `transform(batch) -> GraphWriteBatch`

    Subclasses must NOT:
    - import any DB client, loader, or pipeline module
    - invent mapping rules that belong in app/mappings/
    - construct graph IDs inline — always use app/core/ids.py helpers
    """

    # -- Class-level declarations (overridden by every subclass) --------------

    source_name: str = ""
    """Logical warehouse source/table name. Must match schema SOURCE_NAME."""

    secondary_sources: tuple[str, ...] = ()
    """Additional source names this transformer handles via dispatch on batch.source_name."""

    inclusion_mode: str = ""
    """Inclusion category. Must match schema INCLUSION_MODE."""

    # -- Construction ---------------------------------------------------------

    def __init__(
        self,
        run_id: str,
        canonicalizer_registry: dict[str, BaseCanonicalizer] | None = None,
        mapping_registry: MappingRegistry | None = None,
    ) -> None:
        """
        Initialise the transformer.

        Args:
            run_id:                 Pipeline run ID threaded through all
                                    produced records.
            canonicalizer_registry: Dict of domain canonicalizers keyed by
                                    domain name (e.g. "teams", "tags").
                                    Optional; only required for transformers
                                    that perform canonicalization.
            mapping_registry:       Validated MappingRegistry. Optional;
                                    available to transformers that need to
                                    query routing or ownership rules at
                                    runtime beyond what the static module-
                                    level helpers provide.
        """
        if not run_id or not run_id.strip():
            raise TransformationError(
                "BaseTransformer requires a non-empty run_id",
                source=self.source_name,
            )

        self._run_id: str = run_id
        self._canonicalizers: dict[str, BaseCanonicalizer] = (
            canonicalizer_registry or {}
        )
        self._mapping_registry: MappingRegistry | None = mapping_registry
        self._skip_count: int = 0
        self._logger: ProjectPulseLoggerAdapter = get_logger(
            f"{type(self).__module__}.{type(self).__name__}",
            source=self.source_name,
            run_id=run_id,
        )

    # -- Abstract interface ---------------------------------------------------

    @abstractmethod
    def transform(self, batch: ExtractorBatch) -> GraphWriteBatch:
        """
        Transform a batch of typed warehouse rows into graph write records.

        Args:
            batch: Typed warehouse row batch from an extractor.

        Returns:
            GraphWriteBatch containing NodeRecord and RelationshipRecord
            instances ready for the loader layer.

        Implementation requirements:
        - Call log_transformation_started() at the top.
        - Call log_transformation_finished() at the bottom.
        - Never raise from a per-row error — log and skip instead.
        - Never write to any database.
        - Return an empty GraphWriteBatch for non-emitting sources.
        """

    # -- Type coercion helpers ------------------------------------------------

    def _ts(self, value: datetime | None) -> str | None:
        """
        Normalize a warehouse datetime to an ISO UTC string for graph storage.

        Args:
            value: UTC-aware datetime from a typed row, or None.

        Returns:
            ISO 8601 UTC timestamp string, or None.
        """
        if value is None:
            return None
        return format_iso_timestamp(value)

    def _bool(self, value: int | None) -> bool | None:
        """
        Coerce a TINYINT 0/1 warehouse value to Python bool.

        Warehouse row dataclasses preserve TINYINT fields as int | None.
        Graph node schemas declare the corresponding property as bool | None.
        This helper bridges that boundary.

        Args:
            value: Integer 0 or 1 from a TINYINT warehouse column, or None.

        Returns:
            True if value is truthy, False if zero, None if value is None.
        """
        if value is None:
            return None
        return bool(value)

    def _int(self, value: float | None) -> int | None:
        """
        Truncate a DECIMAL/DOUBLE warehouse value to int for graph storage.

        Used when the graph node schema declares a property as int but the
        warehouse row carries a float (e.g. coin_amount, reward_amount).

        Args:
            value: Float from a DECIMAL/DOUBLE warehouse column, or None.

        Returns:
            Truncated integer, or None.
        """
        if value is None:
            return None
        return int(value)

    # -- Lifecycle helpers ----------------------------------------------------

    def _log_started(self, **context: Any) -> None:
        """Emit a transformation_started structured log event."""
        log_transformation_started(
            self._logger,
            table_name=self.source_name,
            run_id=self._run_id,
            **context,
        )

    def _log_finished(
        self,
        record_count: int | None = None,
        **context: Any,
    ) -> None:
        """Emit a transformation_finished structured log event."""
        log_transformation_finished(
            self._logger,
            record_count=record_count,
            table_name=self.source_name,
            run_id=self._run_id,
            skip_count=self._skip_count,
            **context,
        )

    def _skip(self, reason: str, **context: Any) -> None:
        """
        Record a per-row skip and emit a validation_failed log event.

        Call this instead of raising from inside the per-row loop. The batch
        continues processing; skips are counted and surfaced in the finished
        log event.

        Args:
            reason:   Human-readable reason for the skip.
            **context: Additional structured fields for the log event
                       (e.g. row_id, field_name, raw_value).
        """
        self._skip_count += 1
        log_validation_failure(
            self._logger,
            error=reason,
            table_name=self.source_name,
            run_id=self._run_id,
            **context,
        )

    def _reset_skip_count(self) -> None:
        """Reset the skip counter. Call at the start of each transform() call."""
        self._skip_count = 0

    # -- Canonicalizer registry access ----------------------------------------

    def _get_canonicalizer(self, domain: str) -> BaseCanonicalizer:
        """
        Return the canonicalizer for a given domain.

        Args:
            domain: Canonicalizer domain name, e.g. "teams", "tags",
                    "competitions".

        Returns:
            BaseCanonicalizer instance for the domain.

        Raises:
            TransformationError: If the domain is not present in the
                injected canonicalizer registry.
        """
        canon = self._canonicalizers.get(domain)
        if canon is None:
            raise TransformationError(
                f"Canonicalizer domain '{domain}' was not injected into "
                f"{type(self).__name__}. Ensure the canonicalizer registry "
                f"is built and passed at construction time.",
                source=self.source_name,
                domain=domain,
            )
        return canon

    # -- Endpoint resolution --------------------------------------------------

    def _resolve_endpoint(
        self,
        rel_type: str,
        endpoint_name: str,
        raw_value: Any,
        source_name: str | None = None,
    ) -> str | None:
        """
        Resolve a relationship endpoint node ID using the declared EndpointSpec.

        Reads the EndpointSpec for (rel_type, endpoint_name, source_name) from
        ENDPOINT_SPECS in app/mappings/endpoint_resolution.py. If the spec
        declares a canonicalizer requirement, the appropriate canonicalizer
        method is called. If no canonicalizer is required, the raw value is
        normalized directly via normalize_string_id().

        Args:
            rel_type:       Graph relationship type, e.g. "PREDICTED".
            endpoint_name:  "start" or "end".
            raw_value:      Raw source field value (ID, name, or alias).
            source_name:    Source name for endpoint spec lookup. Defaults to
                            self.source_name. Pass the secondary source name when
                            calling from a multi-source transformer dispatch handler.

        Returns:
            Resolved graph node ID string, or None if resolution fails and
            the endpoint is not required.

        Raises:
            TransformationError: If the endpoint spec declares the canonicalizer
                as required and resolution fails, or if the EndpointSpec is not
                registered for this (rel_type, endpoint_name, source_name) triple.
            TransformationError: If raw_value is None and the endpoint is required.
        """
        _source = source_name or self.source_name
        if raw_value is None:
            spec = get_endpoint_spec(rel_type, endpoint_name, _source)
            if spec.required:
                raise TransformationError(
                    "Required endpoint value is None",
                    rel_type=rel_type,
                    endpoint=endpoint_name,
                    source=_source,
                )
            return None

        spec = get_endpoint_spec(rel_type, endpoint_name, _source)

        if spec.canonicalizer is None:
            return normalize_string_id(raw_value, field_name=spec.id_source_field or endpoint_name)

        canon = self._get_canonicalizer(spec.canonicalizer.domain)
        resolver = getattr(canon, spec.canonicalizer.resolver_method)

        try:
            result: CanonicalForm | None = resolver(raw_value)
        except CanonicalizationError as exc:
            if spec.canonicalizer.required:
                raise TransformationError(
                    "Required endpoint canonicalization raised an error",
                    rel_type=rel_type,
                    endpoint=endpoint_name,
                    raw_value=raw_value,
                    source=_source,
                ) from exc
            return None

        if result is None:
            if spec.canonicalizer.required:
                raise TransformationError(
                    "Required endpoint canonicalization returned None",
                    rel_type=rel_type,
                    endpoint=endpoint_name,
                    raw_value=raw_value,
                    source=_source,
                )
            return None

        return result.canonical_id

    # -- Registry access helpers ----------------------------------------------

    @property
    def mapping_registry(self) -> MappingRegistry | None:
        """Return the injected MappingRegistry, if present."""
        return self._mapping_registry

    @property
    def run_id(self) -> str:
        """Return the pipeline run ID."""
        return self._run_id

    @property
    def skip_count(self) -> int:
        """Return the current per-batch skip count."""
        return self._skip_count

    # -- Repr -----------------------------------------------------------------

    def __repr__(self) -> str:
        return (
            f"{type(self).__name__}("
            f"source={self.source_name!r}, "
            f"run_id={self._run_id!r})"
        )