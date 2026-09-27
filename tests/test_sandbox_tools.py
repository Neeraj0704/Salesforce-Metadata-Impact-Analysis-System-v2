"""Tests for the framework-neutral agent tool adapter."""

import unittest
import tempfile
from pathlib import Path
from unittest.mock import Mock

from metadata_fixtures import build_metadata_zip
from src.pipeline.run import ingest_metadata_archive
from src.sandbox.controller import CommandResult
from src.sandbox.manager import SandboxSessionManager
from src.sandbox.tools import SandboxToolAdapter


class FakeSandbox:
    def __init__(self, session_id: str, workspace: Path) -> None:
        self.workspace = workspace

    def create(self) -> None:
        self.workspace.mkdir(parents=True, exist_ok=True)

    def destroy(self) -> None:
        return None


class SandboxToolAdapterTests(unittest.TestCase):
    def test_returns_serializable_command_result(self) -> None:
        manager = Mock()
        manager.execute.return_value = CommandResult(0, "hello\n", "")
        adapter = SandboxToolAdapter(manager, "abcdef123456")

        result = adapter.run_sandbox_command(
            program="python",
            arguments=["script.py"],
            timeout_seconds=12,
        )

        manager.execute.assert_called_once_with(
            "abcdef123456",
            ["python", "script.py"],
            timeout_seconds=12,
        )
        self.assertEqual(
            result,
            {"exit_code": 0, "succeeded": True, "stdout": "hello\n", "stderr": ""},
        )

    def test_agent_can_request_impact_analysis(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            manager = SandboxSessionManager(
                workspace_root=Path(temporary_directory),
                sandbox_factory=FakeSandbox,
            )
            ingestion = ingest_metadata_archive(build_metadata_zip(), manager)
            adapter = SandboxToolAdapter(manager, ingestion.session.session_id)

            result = adapter.analyze_metadata_impact(
                component_key="CustomField:Invoice__c.Status__c",
                change_type="modify",
            )

            self.assertGreaterEqual(result["direct_impact_count"], 3)
            self.assertIn(result["risk_level"], {"high", "critical"})


if __name__ == "__main__":
    unittest.main()
