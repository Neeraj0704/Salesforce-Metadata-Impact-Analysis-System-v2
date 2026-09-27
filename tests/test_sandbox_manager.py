"""Tests for persistent sandbox session management."""

from datetime import datetime, timedelta, timezone
import tempfile
import unittest
from pathlib import Path

from src.sandbox.controller import CommandResult
from src.sandbox.manager import SandboxSessionManager, SessionNotFound


class FakeSandbox:
    def __init__(self, session_id: str, workspace: Path) -> None:
        self.session_id = session_id
        self.workspace = workspace
        self.created = False
        self.destroyed = False
        self.commands: list[tuple[str, ...]] = []

    def create(self) -> None:
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.created = True

    def execute(
        self,
        command: tuple[str, ...],
        *,
        timeout_seconds: float = 30,
    ) -> CommandResult:
        self.commands.append(command)
        return CommandResult(0, "ok", "")

    def destroy(self) -> None:
        self.destroyed = True


class SandboxSessionManagerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.now = datetime(2026, 9, 27, tzinfo=timezone.utc)
        self.sandboxes: dict[str, FakeSandbox] = {}

        def factory(session_id: str, workspace: Path) -> FakeSandbox:
            sandbox = FakeSandbox(session_id, workspace)
            self.sandboxes[session_id] = sandbox
            return sandbox

        self.manager = SandboxSessionManager(
            workspace_root=Path(self.temporary_directory.name),
            idle_timeout=timedelta(minutes=30),
            sandbox_factory=factory,
            clock=lambda: self.now,
        )

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_same_session_runs_multiple_commands(self) -> None:
        session = self.manager.create_session()

        first = self.manager.execute(session.session_id, ["pwd"])
        second = self.manager.execute(session.session_id, ["python", "script.py"])

        self.assertTrue(first.succeeded)
        self.assertTrue(second.succeeded)
        sandbox = self.sandboxes[session.session_id]
        self.assertEqual(sandbox.commands, [("pwd",), ("python", "script.py")])
        self.assertEqual(self.manager.get_session(session.session_id).command_count, 2)

    def test_destroy_unregisters_session(self) -> None:
        session = self.manager.create_session()
        self.manager.destroy_session(session.session_id)

        self.assertTrue(self.sandboxes[session.session_id].destroyed)
        with self.assertRaises(SessionNotFound):
            self.manager.get_session(session.session_id)

    def test_cleanup_destroys_idle_session(self) -> None:
        session = self.manager.create_session()
        self.now += timedelta(minutes=31)

        expired = self.manager.cleanup_expired()

        self.assertEqual(expired, [session.session_id])
        self.assertTrue(self.sandboxes[session.session_id].destroyed)

    def test_shutdown_destroys_all_sessions(self) -> None:
        first = self.manager.create_session()
        second = self.manager.create_session()

        self.manager.shutdown()

        self.assertTrue(self.sandboxes[first.session_id].destroyed)
        self.assertTrue(self.sandboxes[second.session_id].destroyed)
        self.assertEqual(self.manager.active_session_count, 0)

    def test_destroy_calls_external_session_cleanup(self) -> None:
        cleaned: list[str] = []

        def factory(session_id: str, workspace: Path) -> FakeSandbox:
            return FakeSandbox(session_id, workspace)

        manager = SandboxSessionManager(
            workspace_root=Path(self.temporary_directory.name),
            sandbox_factory=factory,
            session_cleanup=cleaned.append,
        )
        session = manager.create_session()

        manager.destroy_session(session.session_id)

        self.assertEqual(cleaned, [session.session_id])


if __name__ == "__main__":
    unittest.main()
