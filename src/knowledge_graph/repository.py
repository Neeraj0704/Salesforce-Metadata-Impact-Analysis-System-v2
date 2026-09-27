"""Graph repository contract and lightweight SQLite test adapter."""

from __future__ import annotations

import json
import sqlite3
from collections import Counter, deque
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from src.knowledge_graph.models import GraphEdge, GraphNode, GraphSummary, KnowledgeGraph


class GraphNodeNotFound(KeyError):
    """Raised when an impact traversal starts from an unknown component."""


@dataclass(frozen=True)
class TraversedNode:
    node: GraphNode
    distance: int
    parent_key: str
    relationship: str


class GraphRepository(Protocol):
    """Storage contract used by ingestion and impact analysis."""

    backend_name: str

    def replace_graph(self, graph: KnowledgeGraph) -> GraphSummary: ...

    def summary(self) -> GraphSummary: ...

    def get_node(self, key: str) -> GraphNode: ...

    def impacted_components(
        self, key: str, *, max_depth: int = 5
    ) -> list[TraversedNode]: ...

    def clear_graph(self) -> None: ...

    def close(self) -> None: ...


class SQLiteGraphRepository:
    """Store and query one session's graph in a portable SQLite database."""

    backend_name = "sqlite"

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path.expanduser().resolve()

    def initialize(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS nodes (
                    key TEXT PRIMARY KEY,
                    component_type TEXT NOT NULL,
                    name TEXT NOT NULL,
                    source_path TEXT,
                    attributes_json TEXT NOT NULL,
                    is_placeholder INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS edges (
                    source_key TEXT NOT NULL,
                    target_key TEXT NOT NULL,
                    relationship TEXT NOT NULL,
                    source_path TEXT NOT NULL,
                    evidence TEXT,
                    PRIMARY KEY (source_key, target_key, relationship, source_path),
                    FOREIGN KEY (source_key) REFERENCES nodes(key),
                    FOREIGN KEY (target_key) REFERENCES nodes(key)
                );
                CREATE INDEX IF NOT EXISTS idx_edges_target ON edges(target_key);
                CREATE INDEX IF NOT EXISTS idx_edges_source ON edges(source_key);
                """
            )

    def replace_graph(self, graph: KnowledgeGraph) -> GraphSummary:
        """Atomically replace all graph data in this database."""
        self.initialize()
        with self._connect() as connection:
            connection.execute("DELETE FROM edges")
            connection.execute("DELETE FROM nodes")
            connection.executemany(
                """
                INSERT INTO nodes (
                    key, component_type, name, source_path,
                    attributes_json, is_placeholder
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        node.key,
                        node.component_type,
                        node.name,
                        node.source_path,
                        json.dumps(node.attributes, sort_keys=True),
                        int(node.is_placeholder),
                    )
                    for node in graph.nodes
                ],
            )
            connection.executemany(
                """
                INSERT INTO edges (
                    source_key, target_key, relationship, source_path, evidence
                ) VALUES (?, ?, ?, ?, ?)
                """,
                [
                    (
                        edge.source_key,
                        edge.target_key,
                        edge.relationship,
                        edge.source_path,
                        edge.evidence,
                    )
                    for edge in graph.edges
                ],
            )
        return self.summary()

    def clear_graph(self) -> None:
        """Delete every node and edge from the local test graph."""
        if not self.database_path.exists():
            return
        with self._connect() as connection:
            connection.execute("DELETE FROM edges")
            connection.execute("DELETE FROM nodes")

    def close(self) -> None:
        """SQLite connections are scoped to individual method calls."""
        return None

    def summary(self) -> GraphSummary:
        """Return graph counts grouped by node and relationship type."""
        self._require_database()
        with self._connect() as connection:
            node_rows = connection.execute(
                "SELECT component_type, is_placeholder FROM nodes"
            ).fetchall()
            edge_rows = connection.execute("SELECT relationship FROM edges").fetchall()
        component_types = Counter(row["component_type"] for row in node_rows)
        relationship_types = Counter(row["relationship"] for row in edge_rows)
        return GraphSummary(
            node_count=len(node_rows),
            edge_count=len(edge_rows),
            placeholder_count=sum(row["is_placeholder"] for row in node_rows),
            component_types=dict(sorted(component_types.items())),
            relationship_types=dict(sorted(relationship_types.items())),
        )

    def get_node(self, key: str) -> GraphNode:
        """Return one graph node by its stable metadata key."""
        self._require_database()
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM nodes WHERE key = ?", (key,)).fetchone()
        if row is None:
            raise GraphNodeNotFound(key)
        return self._node_from_row(row)

    def impacted_components(self, key: str, *, max_depth: int = 5) -> list[TraversedNode]:
        """Traverse components that depend on the changed component."""
        if max_depth < 1:
            raise ValueError("max_depth must be at least one")
        self.get_node(key)
        discovered: dict[str, TraversedNode] = {}
        queue: deque[tuple[str, int]] = deque([(key, 0)])

        with self._connect() as connection:
            while queue:
                current_key, distance = queue.popleft()
                if distance >= max_depth:
                    continue
                rows = connection.execute(
                    """
                    SELECT source_key AS impacted_key, relationship
                    FROM edges
                    WHERE target_key = ?
                    UNION
                    SELECT target_key AS impacted_key, relationship
                    FROM edges
                    WHERE source_key = ? AND relationship = 'HAS_FIELD'
                    """,
                    (current_key, current_key),
                ).fetchall()
                for row in rows:
                    impacted_key = row["impacted_key"]
                    if impacted_key == key or impacted_key in discovered:
                        continue
                    node_row = connection.execute(
                        "SELECT * FROM nodes WHERE key = ?", (impacted_key,)
                    ).fetchone()
                    if node_row is None:
                        continue
                    traversed = TraversedNode(
                        node=self._node_from_row(node_row),
                        distance=distance + 1,
                        parent_key=current_key,
                        relationship=row["relationship"],
                    )
                    discovered[impacted_key] = traversed
                    queue.append((impacted_key, distance + 1))

        return sorted(
            discovered.values(),
            key=lambda item: (item.distance, item.node.component_type, item.node.key),
        )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _require_database(self) -> None:
        if not self.database_path.is_file():
            raise FileNotFoundError(f"Knowledge graph does not exist: {self.database_path}")

    @staticmethod
    def _node_from_row(row: sqlite3.Row) -> GraphNode:
        return GraphNode(
            key=row["key"],
            component_type=row["component_type"],
            name=row["name"],
            source_path=row["source_path"],
            attributes=json.loads(row["attributes_json"]),
            is_placeholder=bool(row["is_placeholder"]),
        )
