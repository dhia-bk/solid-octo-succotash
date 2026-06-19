"""
Exception hierarchy for Project Pulse Knowledge Graph.

Design goals:
- Provide one root exception for all platform-specific failures.
- Keep exceptions specific and grouped by domain.
- Allow optional structured context for logs, retries, and alerts.
- Avoid runtime logic unrelated to exception modeling.

Usage example:
    raise ConfigurationError(
        "Missing required configuration value",
        config_key="mysql.host",
        env="prod",
    )
"""

from __future__ import annotations

from typing import Any


class ProjectPulseError(Exception):
    """
    Root exception for all Project Pulse platform errors.

    Attributes:
        message: Human-readable error message.
        context: Optional structured context fields such as:
            - table_name
            - pipeline_name
            - run_id
            - config_key
            - graph_name
            - env
    """

    def __init__(self, message: str, **context: Any) -> None:
        self.message = message
        self.context: dict[str, Any] = context
        super().__init__(self.__str__())

    def __str__(self) -> str:
        if not self.context:
            return self.message

        context_str = ", ".join(f"{key}={value!r}" for key, value in sorted(self.context.items()))
        return f"{self.message} | context: {context_str}"


# Configuration / runtime exceptions


class ConfigurationError(ProjectPulseError):
    """Raised when application configuration is missing, invalid, or inconsistent."""


class MissingEnvironmentVariableError(ConfigurationError):
    """Raised when a required environment variable is not present."""


class InvalidConfigError(ConfigurationError):
    """Raised when configuration values fail validation rules."""


class InvalidEnvironmentError(ConfigurationError):
    """Raised when an unsupported runtime environment is requested."""


class RuntimeStateError(ProjectPulseError):
    """Raised when the application enters an invalid runtime state."""


# Data / source / schema exceptions


class SourceInventoryError(ProjectPulseError):
    """Raised when source inventory metadata is missing, invalid, or out of sync."""


class SourceInclusionError(ProjectPulseError):
    """Raised when source inclusion rules are invalid or inconsistent."""


class SchemaMappingError(ProjectPulseError):
    """Raised when warehouse-to-graph mapping definitions are invalid or incomplete."""


class ExtractorError(ProjectPulseError):
    """Raised when source extraction fails."""


class TransformationError(ProjectPulseError):
    """Raised when data transformation or normalization fails."""


class CanonicalizationError(TransformationError):
    """Raised when entity canonicalization fails or produces ambiguous output."""


class ValidationError(ProjectPulseError):
    """Raised when validation checks fail."""


class SourceValidationError(ValidationError):
    """Raised when source-side validation checks fail."""


class GraphValidationError(ValidationError):
    """Raised when graph integrity or graph-side validation checks fail."""


class ReconciliationError(ValidationError):
    """Raised when source-to-graph reconciliation checks fail."""


# Database / persistence exceptions


class DatabaseError(ProjectPulseError):
    """Base exception for persistence and database-related failures."""


class WarehouseConnectionError(DatabaseError):
    """Raised when the warehouse connection cannot be established or used."""


class WarehouseQueryError(DatabaseError):
    """Raised when a warehouse query fails."""


class GraphConnectionError(DatabaseError):
    """Raised when the Neo4j graph connection cannot be established or used."""


class GraphQueryError(DatabaseError):
    """Raised when a Neo4j query fails."""


class MetadataDatabaseError(DatabaseError):
    """Raised when metadata database operations fail."""


class CheckpointError(DatabaseError):
    """Raised when checkpoint creation, retrieval, or update fails."""


class JobRunPersistenceError(DatabaseError):
    """Raised when job run metadata cannot be written or updated."""


class ModelRegistryError(DatabaseError):
    """Raised when model registry operations fail."""


# Loader / pipeline exceptions


class LoaderError(ProjectPulseError):
    """Raised when graph loading or batch writing fails."""


class ConstraintError(LoaderError):
    """Raised when graph constraint or index setup fails."""


class BatchWriteError(LoaderError):
    """Raised when a batch write to the graph fails."""


class PipelineError(ProjectPulseError):
    """Raised when a pipeline execution fails."""


class PipelineDependencyError(PipelineError):
    """Raised when a required pipeline dependency is missing or incomplete."""


class PipelineConfigurationError(PipelineError):
    """Raised when pipeline-level configuration is invalid."""


# Analytics / GDS / inference exceptions


class AnalyticsError(ProjectPulseError):
    """Base exception for graph analytics failures."""


class ProjectionError(AnalyticsError):
    """Raised when a graph projection cannot be created or validated."""


class MemoryEstimationError(AnalyticsError):
    """Raised when memory estimation fails or exceeds allowed limits."""


class LeidenExecutionError(AnalyticsError):
    """Raised when Leiden community detection fails."""


class CentralityExecutionError(AnalyticsError):
    """Raised when centrality or PageRank jobs fail."""


class InferenceError(AnalyticsError):
    """Raised when inference execution or inference write-back fails."""


class ConfidenceScoringError(AnalyticsError):
    """Raised when confidence score computation fails."""


class EvaluationError(AnalyticsError):
    """Raised when analytics evaluation or benchmark checks fail."""


class ModelVersionError(AnalyticsError):
    """Raised when model versions are missing, incompatible, or invalid."""


# Serving / API exceptions


class ServingError(ProjectPulseError):
    """Base exception for serving-layer failures."""


class ServingMaterializationError(ServingError):
    """Raised when serving views or materialized outputs cannot be built."""


class FeatureMaterializationError(ServingError):
    """Raised when feature summaries cannot be materialized for serving."""


class APIError(ProjectPulseError):
    """Base exception for API-facing failures."""


class ResourceNotFoundError(APIError):
    """Raised when a requested resource does not exist."""


class BadRequestError(APIError):
    """Raised when a request is malformed or invalid."""


class UnauthorizedError(APIError):
    """Raised when authentication is missing or invalid."""


class ForbiddenError(APIError):
    """Raised when the caller is authenticated but not allowed to access a resource."""


class ConflictError(APIError):
    """Raised when an operation conflicts with the current system state."""


# Scheduler / orchestration exceptions


class SchedulerError(ProjectPulseError):
    """Raised when scheduler or recurring job orchestration fails."""


class JobExecutionError(SchedulerError):
    """Raised when a scheduled job fails during execution."""


class DependencyResolutionError(SchedulerError):
    """Raised when a scheduled job cannot resolve required runtime dependencies."""
