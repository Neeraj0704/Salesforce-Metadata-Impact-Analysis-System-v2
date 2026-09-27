"""Tests for sandbox HTTP endpoints."""

from datetime import timedelta
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from metadata_fixtures import build_metadata_zip
from main import app
from src.api.dependencies import get_sandbox_manager
from src.pipeline.run import ingest_metadata_archive
from src.sandbox.controller import CommandResult
from src.sandbox.manager import SandboxSessionManager


class FakeSandbox:
    def __init__(self, session_id: str, workspace: Path) -> None:
        self.workspace = workspace

    def create(self) -> None:
        self.workspace.mkdir(parents=True, exist_ok=True)

    def execute(
        self,
        command: tuple[str, ...],
        *,
        timeout_seconds: float = 30,
    ) -> CommandResult:
        return CommandResult(0, " ".join(command), "")

    def destroy(self) -> None:
        return None


class SandboxApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.manager = SandboxSessionManager(
            workspace_root=Path(self.temporary_directory.name),
            idle_timeout=timedelta(minutes=30),
            sandbox_factory=FakeSandbox,
        )
        app.dependency_overrides[get_sandbox_manager] = lambda: self.manager
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.client.close()
        app.dependency_overrides.clear()
        self.temporary_directory.cleanup()

    def test_complete_session_lifecycle(self) -> None:
        created = self.client.post("/sandbox/sessions")
        self.assertEqual(created.status_code, 201)
        session_id = created.json()["session_id"]

        command = self.client.post(
            f"/sandbox/sessions/{session_id}/commands",
            json={"program": "python", "arguments": ["script.py"]},
        )
        self.assertEqual(command.status_code, 200)
        self.assertEqual(command.json()["stdout"], "python script.py")

        status_response = self.client.get(f"/sandbox/sessions/{session_id}")
        self.assertEqual(status_response.json()["command_count"], 1)

        destroyed = self.client.delete(f"/sandbox/sessions/{session_id}")
        self.assertEqual(destroyed.status_code, 200)
        self.assertTrue(destroyed.json()["destroyed"])

        missing = self.client.get(f"/sandbox/sessions/{session_id}")
        self.assertEqual(missing.status_code, 404)

    def test_rejects_disallowed_program(self) -> None:
        session_id = self.client.post("/sandbox/sessions").json()["session_id"]
        response = self.client.post(
            f"/sandbox/sessions/{session_id}/commands",
            json={"program": "docker", "arguments": ["ps"]},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("not allowed", response.json()["detail"])

    def test_metadata_is_missing_for_empty_session(self) -> None:
        session_id = self.client.post("/sandbox/sessions").json()["session_id"]
        response = self.client.get(f"/sandbox/sessions/{session_id}/metadata")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "Session has no parsed metadata")

    def test_returns_parsed_metadata_for_ingested_session(self) -> None:
        ingestion = ingest_metadata_archive(build_metadata_zip(), self.manager)

        response = self.client.get(
            f"/sandbox/sessions/{ingestion.session.session_id}/metadata"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["components"]), 7)


if __name__ == "__main__":
    unittest.main()
