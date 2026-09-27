"""Tests for archive import and parsing inside one sandbox session."""

import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

from metadata_fixtures import build_metadata_zip
from src.pipeline.run import ingest_metadata_archive
from src.sandbox.controller import CommandResult
from src.sandbox.manager import SandboxSessionManager


class FakeSandbox:
    def __init__(self, session_id: str, workspace: Path) -> None:
        self.workspace = workspace
        self.destroyed = False

    def create(self) -> None:
        self.workspace.mkdir(parents=True, exist_ok=True)

    def execute(
        self,
        command: tuple[str, ...],
        *,
        timeout_seconds: float = 30,
    ) -> CommandResult:
        return CommandResult(0, "", "")

    def destroy(self) -> None:
        self.destroyed = True


class IngestionPipelineTests(unittest.TestCase):
    def test_archive_is_imported_and_parsed_in_session_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            manager = SandboxSessionManager(
                workspace_root=Path(temporary_directory),
                idle_timeout=timedelta(minutes=30),
                sandbox_factory=FakeSandbox,
            )

            result = ingest_metadata_archive(build_metadata_zip(), manager)

            workspace = manager.get_workspace(result.session.session_id)
            self.assertEqual(result.archive.file_count, 6)
            self.assertGreaterEqual(result.parsed.component_count, 7)
            self.assertTrue((workspace / "metadata/unpackaged/package.xml").is_file())
            self.assertTrue(result.parsed_output_path.is_file())
            manager.destroy_session(result.session.session_id)


if __name__ == "__main__":
    unittest.main()
