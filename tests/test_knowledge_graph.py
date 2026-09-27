"""Tests for graph construction, persistence, and impact traversal."""

import tempfile
import unittest
from pathlib import Path

from metadata_fixtures import build_metadata_zip
from src.impact_analysis.analyzer import analyze_impact
from src.knowledge_graph.builder import build_knowledge_graph
from src.knowledge_graph.repository import GraphNodeNotFound, SQLiteGraphRepository
from src.metadata_api.zip_extractor import extract_zip_to_directory
from src.metadata_parser.service import parse_metadata_workspace


class KnowledgeGraphTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        workspace = Path(self.temporary_directory.name)
        metadata_root = workspace / "metadata"
        extract_zip_to_directory(build_metadata_zip(), metadata_root)
        parsed = parse_metadata_workspace(metadata_root)
        graph = build_knowledge_graph(parsed)
        self.repository = SQLiteGraphRepository(workspace / "knowledge_graph.db")
        self.summary = self.repository.replace_graph(graph)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_builds_nodes_edges_and_unresolved_placeholders(self) -> None:
        self.assertGreaterEqual(self.summary.node_count, 8)
        self.assertGreaterEqual(self.summary.edge_count, 10)
        self.assertGreaterEqual(self.summary.placeholder_count, 1)
        account = self.repository.get_node("CustomObject:Account")
        self.assertTrue(account.is_placeholder)

    def test_traverses_direct_and_indirect_dependents(self) -> None:
        impacted = self.repository.impacted_components(
            "CustomField:Invoice__c.Status__c"
        )
        distances = {item.node.key: item.distance for item in impacted}

        self.assertEqual(distances["Flow:Update_Invoice"], 1)
        self.assertEqual(distances["PermissionSet:Invoice_User"], 1)
        self.assertEqual(distances["CustomObject:Invoice__c"], 1)
        self.assertEqual(distances["ApexClass:InvoiceService"], 2)
        self.assertEqual(distances["ApexTrigger:InvoiceTrigger"], 2)

    def test_returns_explainable_risk_report(self) -> None:
        report = analyze_impact(
            self.repository,
            "CustomField:Invoice__c.Status__c",
            change_type="modify",
        )

        self.assertGreaterEqual(report.risk_score, 50)
        self.assertIn(report.risk_level, {"high", "critical"})
        self.assertEqual(report.direct_impact_count, 3)
        self.assertTrue(any("depend directly" in reason for reason in report.reasons))

    def test_unknown_component_is_rejected(self) -> None:
        with self.assertRaises(GraphNodeNotFound):
            analyze_impact(self.repository, "CustomField:Missing.Field__c")


if __name__ == "__main__":
    unittest.main()
