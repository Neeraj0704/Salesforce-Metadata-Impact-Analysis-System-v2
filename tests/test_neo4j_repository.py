"""Driver-contract tests for Neo4j graph persistence."""

import unittest
from unittest.mock import MagicMock

from src.knowledge_graph.models import GraphEdge, GraphNode, KnowledgeGraph
from src.knowledge_graph.neo4j_repository import Neo4jGraphRepository


class Neo4jRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.driver = MagicMock()
        self.session = MagicMock()
        self.driver.session.return_value.__enter__.return_value = self.session
        self.transaction = MagicMock()
        self.transaction.run.return_value.consume.return_value = None

        def execute_write(callback, nodes, edges):
            return callback(self.transaction, nodes, edges)

        self.session.execute_write.side_effect = execute_write
        self.repository = Neo4jGraphRepository(
            uri="bolt://example:7687",
            user="neo4j",
            password="password",
            database="neo4j",
            session_id="abcdef123456",
            driver=self.driver,
        )

    def test_replace_graph_namespaces_nodes_and_edges(self) -> None:
        graph = KnowledgeGraph(
            nodes=[
                GraphNode(
                    key="CustomObject:Account",
                    component_type="CustomObject",
                    name="Account",
                ),
                GraphNode(
                    key="Flow:Update_Account",
                    component_type="Flow",
                    name="Update_Account",
                ),
            ],
            edges=[
                GraphEdge(
                    source_key="Flow:Update_Account",
                    target_key="CustomObject:Account",
                    relationship="USES_OBJECT",
                    source_path="flows/Update_Account.flow",
                )
            ],
        )
        self.driver.execute_query.side_effect = [
            ([], None, []),
            (
                [
                    {"component_type": "CustomObject", "is_placeholder": False},
                    {"component_type": "Flow", "is_placeholder": False},
                ],
                None,
                [],
            ),
            ([{"relationship": "USES_OBJECT"}], None, []),
        ]

        summary = self.repository.replace_graph(graph)

        self.assertEqual(summary.node_count, 2)
        self.assertEqual(summary.edge_count, 1)
        _, nodes, edges = self.session.execute_write.call_args.args
        self.assertEqual(nodes[0]["session_id"], "abcdef123456")
        self.assertTrue(nodes[0]["graph_key"].startswith("abcdef123456:"))
        self.assertEqual(edges[0]["relationship"], "USES_OBJECT")

    def test_clear_graph_is_scoped_to_session(self) -> None:
        self.driver.execute_query.return_value = ([], None, [])

        self.repository.clear_graph()

        query = self.driver.execute_query.call_args.args[0]
        self.assertIn("session_id", query)
        self.assertEqual(
            self.driver.execute_query.call_args.kwargs["session_id"],
            "abcdef123456",
        )


if __name__ == "__main__":
    unittest.main()
