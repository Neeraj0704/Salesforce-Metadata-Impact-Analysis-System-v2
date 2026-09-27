"""Unit tests for the Docker sandbox lifecycle."""

import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.sandbox.controller import DockerSandbox, SandboxError


class DockerSandboxTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temporary_directory.name) / "workspace"
        self.sandbox = DockerSandbox(
            session_id="abcdef123456",
            workspace=self.workspace,
        )

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    @patch("src.sandbox.controller.subprocess.run")
    def test_container_persists_across_commands(self, run: unittest.mock.Mock) -> None:
        run.return_value = subprocess.CompletedProcess([], 0, "output", "")

        self.sandbox.create()
        first = self.sandbox.execute(["python", "--version"])
        second = self.sandbox.execute(["pwd"])

        self.assertTrue(first.succeeded)
        self.assertTrue(second.succeeded)
        self.assertEqual(run.call_args_list[1].args[0][:3], ["docker", "exec", "agent-sandbox-abcdef123456"])
        self.assertEqual(run.call_args_list[2].args[0][:3], ["docker", "exec", "agent-sandbox-abcdef123456"])

    @patch("src.sandbox.controller.subprocess.run")
    def test_destroy_removes_container_and_workspace(self, run: unittest.mock.Mock) -> None:
        run.return_value = subprocess.CompletedProcess([], 0, "", "")
        self.sandbox.create()

        self.sandbox.destroy()

        self.assertFalse(self.workspace.exists())
        self.assertEqual(
            run.call_args_list[-1].args[0],
            ["docker", "rm", "--force", "agent-sandbox-abcdef123456"],
        )

    def test_execute_requires_active_session(self) -> None:
        with self.assertRaisesRegex(SandboxError, "has not been created"):
            self.sandbox.execute(["pwd"])

    def test_rejects_invalid_session_id(self) -> None:
        with self.assertRaises(ValueError):
            DockerSandbox(session_id="unsafe name", workspace=self.workspace)


if __name__ == "__main__":
    unittest.main()
