"""Convert normalized parser output into graph nodes and edges."""

from __future__ import annotations

from src.knowledge_graph.models import GraphEdge, GraphNode, KnowledgeGraph
from src.metadata_parser.models import ParseResult


def _placeholder_node(key: str) -> GraphNode:
    component_type, separator, name = key.partition(":")
    if not separator:
        component_type = "Unknown"
        name = key
    return GraphNode(
        key=key,
        component_type=component_type,
        name=name,
        is_placeholder=True,
    )


def build_knowledge_graph(parsed: ParseResult) -> KnowledgeGraph:
    """Build a graph and add placeholder nodes for unresolved references."""
    nodes = {
        component.key: GraphNode(
            key=component.key,
            component_type=component.component_type,
            name=component.name,
            source_path=component.source_path,
            attributes=component.attributes,
        )
        for component in parsed.components
    }
    edges: dict[tuple[str, str, str, str], GraphEdge] = {}

    for reference in parsed.references:
        nodes.setdefault(reference.source_key, _placeholder_node(reference.source_key))
        nodes.setdefault(reference.target_key, _placeholder_node(reference.target_key))
        edge = GraphEdge(
            source_key=reference.source_key,
            target_key=reference.target_key,
            relationship=reference.relationship,
            source_path=reference.source_path,
            evidence=reference.evidence,
        )
        edges[
            (
                edge.source_key,
                edge.target_key,
                edge.relationship,
                edge.source_path,
            )
        ] = edge

    return KnowledgeGraph(
        nodes=sorted(nodes.values(), key=lambda item: item.key),
        edges=sorted(
            edges.values(),
            key=lambda item: (
                item.source_key,
                item.relationship,
                item.target_key,
                item.source_path,
            ),
        ),
    )
