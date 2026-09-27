"""Neo4j-backed storage and traversal for session knowledge graphs."""

from __future__ import annotations

import json
from collections import Counter, deque
from typing import Any

from neo4j import Driver, GraphDatabase, RoutingControl

from src.knowledge_graph.models import GraphNode, GraphSummary, KnowledgeGraph
from src.knowledge_graph.repository import GraphNodeNotFound, TraversedNode


class Neo4jGraphRepository:
    """Store one session graph in Neo4j using a session namespace."""

    backend_name = "neo4j"

    def __init__(
        self,
        *,
        uri: str,
        user: str,
        password: str,
        database: str,
        session_id: str,
        driver: Driver | None = None,
    ) -> None:
        self.database = database
        self.session_id = session_id
        self._owns_driver = driver is None
        self.driver = driver or GraphDatabase.driver(
            uri,
            auth=(user, password),
            telemetry_disabled=True,
        )

    def verify_connectivity(self) -> None:
        self.driver.verify_connectivity()

    def initialize(self) -> None:
        self.driver.execute_query(
            """
            CREATE CONSTRAINT metadata_graph_key IF NOT EXISTS
            FOR (node:MetadataComponent)
            REQUIRE node.graph_key IS UNIQUE
            """,
            database_=self.database,
        )

    def replace_graph(self, graph: KnowledgeGraph) -> GraphSummary:
        """Atomically replace this session's namespaced graph."""
        self.initialize()
        nodes = [
            {
                "graph_key": self._graph_key(node.key),
                "session_id": self.session_id,
                "key": node.key,
                "component_type": node.component_type,
                "name": node.name,
                "source_path": node.source_path,
                "attributes_json": json.dumps(node.attributes, sort_keys=True),
                "is_placeholder": node.is_placeholder,
            }
            for node in graph.nodes
        ]
        edges = [
            {
                "source_graph_key": self._graph_key(edge.source_key),
                "target_graph_key": self._graph_key(edge.target_key),
                "session_id": self.session_id,
                "relationship": edge.relationship,
                "source_path": edge.source_path,
                "evidence": edge.evidence,
            }
            for edge in graph.edges
        ]

        with self.driver.session(database=self.database) as session:
            session.execute_write(self._replace_graph_transaction, nodes, edges)
        return self.summary()

    @staticmethod
    def _replace_graph_transaction(transaction: Any, nodes: list[dict], edges: list[dict]) -> None:
        if nodes:
            session_id = nodes[0]["session_id"]
        elif edges:
            session_id = edges[0]["session_id"]
        else:
            raise ValueError("Cannot persist a graph without nodes")
        transaction.run(
            "MATCH (node:MetadataComponent {session_id: $session_id}) DETACH DELETE node",
            session_id=session_id,
        ).consume()
        transaction.run(
            """
            UNWIND $nodes AS item
            CREATE (node:MetadataComponent)
            SET node = item
            """,
            nodes=nodes,
        ).consume()
        if edges:
            transaction.run(
                """
                UNWIND $edges AS item
                MATCH (source:MetadataComponent {graph_key: item.source_graph_key})
                MATCH (target:MetadataComponent {graph_key: item.target_graph_key})
                CREATE (source)-[:METADATA_RELATION {
                    session_id: item.session_id,
                    relationship: item.relationship,
                    source_path: item.source_path,
                    evidence: item.evidence
                }]->(target)
                """,
                edges=edges,
            ).consume()

    def clear_graph(self) -> None:
        self.driver.execute_query(
            "MATCH (node:MetadataComponent {session_id: $session_id}) DETACH DELETE node",
            session_id=self.session_id,
            database_=self.database,
        )

    def summary(self) -> GraphSummary:
        node_records, _, _ = self.driver.execute_query(
            """
            MATCH (node:MetadataComponent {session_id: $session_id})
            RETURN node.component_type AS component_type,
                   node.is_placeholder AS is_placeholder
            """,
            session_id=self.session_id,
            database_=self.database,
            routing_=RoutingControl.READ,
        )
        edge_records, _, _ = self.driver.execute_query(
            """
            MATCH (:MetadataComponent {session_id: $session_id})
                  -[edge:METADATA_RELATION]->
                  (:MetadataComponent {session_id: $session_id})
            RETURN edge.relationship AS relationship
            """,
            session_id=self.session_id,
            database_=self.database,
            routing_=RoutingControl.READ,
        )
        component_types = Counter(record["component_type"] for record in node_records)
        relationship_types = Counter(record["relationship"] for record in edge_records)
        return GraphSummary(
            node_count=len(node_records),
            edge_count=len(edge_records),
            placeholder_count=sum(bool(record["is_placeholder"]) for record in node_records),
            component_types=dict(sorted(component_types.items())),
            relationship_types=dict(sorted(relationship_types.items())),
        )

    def get_node(self, key: str) -> GraphNode:
        records, _, _ = self.driver.execute_query(
            """
            MATCH (node:MetadataComponent {session_id: $session_id, key: $key})
            RETURN node {.*} AS node
            """,
            session_id=self.session_id,
            key=key,
            database_=self.database,
            routing_=RoutingControl.READ,
        )
        if not records:
            raise GraphNodeNotFound(key)
        return self._node_from_mapping(records[0]["node"])

    def impacted_components(self, key: str, *, max_depth: int = 5) -> list[TraversedNode]:
        if max_depth < 1:
            raise ValueError("max_depth must be at least one")
        self.get_node(key)
        discovered: dict[str, TraversedNode] = {}
        queue: deque[tuple[str, int]] = deque([(key, 0)])

        while queue:
            current_key, distance = queue.popleft()
            if distance >= max_depth:
                continue
            records, _, _ = self.driver.execute_query(
                """
                MATCH (source:MetadataComponent {session_id: $session_id})
                      -[edge:METADATA_RELATION]->
                      (target:MetadataComponent {session_id: $session_id, key: $key})
                RETURN source {.*} AS node, edge.relationship AS relationship
                UNION
                MATCH (source:MetadataComponent {session_id: $session_id, key: $key})
                      -[edge:METADATA_RELATION {relationship: 'HAS_FIELD'}]->
                      (target:MetadataComponent {session_id: $session_id})
                RETURN target {.*} AS node, edge.relationship AS relationship
                """,
                session_id=self.session_id,
                key=current_key,
                database_=self.database,
                routing_=RoutingControl.READ,
            )
            for record in records:
                node = self._node_from_mapping(record["node"])
                if node.key == key or node.key in discovered:
                    continue
                traversed = TraversedNode(
                    node=node,
                    distance=distance + 1,
                    parent_key=current_key,
                    relationship=record["relationship"],
                )
                discovered[node.key] = traversed
                queue.append((node.key, distance + 1))

        return sorted(
            discovered.values(),
            key=lambda item: (item.distance, item.node.component_type, item.node.key),
        )

    def close(self) -> None:
        if self._owns_driver:
            self.driver.close()

    def _graph_key(self, key: str) -> str:
        return f"{self.session_id}:{key}"

    @staticmethod
    def _node_from_mapping(node: dict[str, Any]) -> GraphNode:
        return GraphNode(
            key=node["key"],
            component_type=node["component_type"],
            name=node["name"],
            source_path=node.get("source_path"),
            attributes=json.loads(node.get("attributes_json") or "{}"),
            is_placeholder=bool(node.get("is_placeholder")),
        )
