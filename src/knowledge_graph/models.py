"""Models used by the knowledge graph builder and repository."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class GraphNode(BaseModel):
    model_config = ConfigDict(frozen=True)

    key: str
    component_type: str
    name: str
    source_path: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)
    is_placeholder: bool = False


class GraphEdge(BaseModel):
    model_config = ConfigDict(frozen=True)

    source_key: str
    target_key: str
    relationship: str
    source_path: str
    evidence: str | None = None


class KnowledgeGraph(BaseModel):
    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)


class GraphSummary(BaseModel):
    node_count: int
    edge_count: int
    placeholder_count: int
    component_types: dict[str, int]
    relationship_types: dict[str, int]
