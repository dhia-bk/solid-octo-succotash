"""
app/pipelines — pipeline orchestration layer for Project Pulse Knowledge Graph.

Public API:
- PipelineResult, SourceRunResult: result containers
- PipelineContext, build_pipeline_context: dependency wiring
- BasePipeline: base class for domain pipelines
- PipelineOrchestrator: run pipelines in dependency order
- PIPELINE_REGISTRY: name → class mapping (populated on first import)
- FullBackfillPipeline: full-refresh run of all domain pipelines
- IncrementalPipeline: checkpoint-respecting run of all domain pipelines
"""

from __future__ import annotations

from app.pipelines.base import (
    BasePipeline,
    PipelineContext,
    PipelineResult,
    SourceRunResult,
    build_pipeline_context,
)
from app.pipelines.full_backfill_pipeline import FullBackfillPipeline
from app.pipelines.incremental_pipeline import IncrementalPipeline
from app.pipelines.orchestration import (
    PIPELINE_REGISTRY,
    PipelineOrchestrator,
    _register_pipelines,
)

# Populate the registry on import so callers don't need to call _register_pipelines
_register_pipelines()

__all__ = [
    "BasePipeline",
    "PipelineContext",
    "PipelineResult",
    "SourceRunResult",
    "build_pipeline_context",
    "PipelineOrchestrator",
    "PIPELINE_REGISTRY",
    "FullBackfillPipeline",
    "IncrementalPipeline",
]
