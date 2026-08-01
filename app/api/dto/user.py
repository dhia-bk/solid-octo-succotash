from __future__ import annotations

from pydantic import BaseModel, Field


class GraphNodeDTO(BaseModel):
    id: str
    labels: list[str] = Field(default_factory=list)
    properties: dict[str, object] = Field(default_factory=dict)


class GraphEdgeDTO(BaseModel):
    source: str
    target: str
    type: str
    properties: dict[str, object] = Field(default_factory=dict)


class UserSubgraphDTO(BaseModel):
    user_id: str
    nodes: list[GraphNodeDTO] = Field(default_factory=list)
    edges: list[GraphEdgeDTO] = Field(default_factory=list)
