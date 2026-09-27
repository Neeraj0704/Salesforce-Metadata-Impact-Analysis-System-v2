"""Impact traversal and explainable deterministic risk scoring."""

from __future__ import annotations

from src.impact_analysis.models import ChangeType, ImpactReport, ImpactedComponent
from src.knowledge_graph.repository import GraphRepository


_CHANGE_BASE_SCORES: dict[str, int] = {"add": 5, "modify": 20, "delete": 35}
_HIGH_RISK_TYPES = {"ApexTrigger", "Flow"}


def _risk_level(score: int) -> str:
    if score >= 75:
        return "critical"
    if score >= 50:
        return "high"
    if score >= 25:
        return "medium"
    return "low"


def analyze_impact(
    repository: GraphRepository,
    component_key: str,
    *,
    change_type: ChangeType = "modify",
    max_depth: int = 5,
) -> ImpactReport:
    """Find dependent components and score the proposed metadata change."""
    changed_component = repository.get_node(component_key)
    traversed = repository.impacted_components(component_key, max_depth=max_depth)
    impacted = [
        ImpactedComponent(
            key=item.node.key,
            component_type=item.node.component_type,
            name=item.node.name,
            distance=item.distance,
            parent_key=item.parent_key,
            relationship=item.relationship,
        )
        for item in traversed
    ]
    direct_count = sum(item.distance == 1 for item in traversed)
    indirect_count = len(traversed) - direct_count
    high_risk_count = sum(
        item.node.component_type in _HIGH_RISK_TYPES for item in traversed
    )

    base_score = _CHANGE_BASE_SCORES[change_type]
    direct_score = min(direct_count * 8, 32)
    indirect_score = min(indirect_count * 3, 24)
    automation_score = min(high_risk_count * 5, 15)
    score = min(base_score + direct_score + indirect_score + automation_score, 100)

    reasons = [f"{change_type.title()} change starts with a base score of {base_score}."]
    if direct_count:
        reasons.append(f"{direct_count} component(s) depend directly on the change.")
    if indirect_count:
        reasons.append(f"{indirect_count} component(s) are affected indirectly.")
    if high_risk_count:
        reasons.append(
            f"{high_risk_count} affected automation component(s) increase execution risk."
        )
    if changed_component.is_placeholder:
        reasons.append("The changed component is referenced but its metadata was not retrieved.")
    if not impacted:
        reasons.append("No dependent components were found in the current graph.")

    return ImpactReport(
        changed_component=changed_component,
        change_type=change_type,
        risk_score=score,
        risk_level=_risk_level(score),
        direct_impact_count=direct_count,
        indirect_impact_count=indirect_count,
        impacted_components=impacted,
        reasons=reasons,
    )
