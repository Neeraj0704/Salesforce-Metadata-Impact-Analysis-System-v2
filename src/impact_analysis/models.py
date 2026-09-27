"""Models returned by the impact-analysis engine."""

from typing import Literal

from pydantic import BaseModel, Field

from src.knowledge_graph.models import GraphNode


ChangeType = Literal["add", "modify", "delete"]
RiskLevel = Literal["low", "medium", "high", "critical"]


class ImpactedComponent(BaseModel):
    key: str
    component_type: str
    name: str
    distance: int
    parent_key: str
    relationship: str


class ImpactReport(BaseModel):
    changed_component: GraphNode
    change_type: ChangeType
    risk_score: int = Field(..., ge=0, le=100)
    risk_level: RiskLevel
    direct_impact_count: int
    indirect_impact_count: int
    impacted_components: list[ImpactedComponent]
    reasons: list[str]
