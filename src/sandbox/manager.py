"""Track Docker sandboxes for the lifetime of application sessions."""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from src.metadata_api.zip_extractor import ExtractedArchive, extract_zip_to_directory
from src.sandbox.controller import CommandResult, DockerSandbox, SandboxError
from src.sandbox.policy import CommandPolicy


class SessionNotFound(KeyError):
    """Raised when a sandbox session ID is unknown."""


@dataclass
class SandboxSession:
    """Mutable lifecycle information for one sandbox session."""

    session_id: str
    sandbox: DockerSandbox
    created_at: datetime
    last_activity_at: datetime
    command_count: int = 0
    lock: threading.Lock = field(default_factory=threading.Lock, repr=False)


@dataclass(frozen=True)
class SessionSnapshot:
    """Public, immutable view of a sandbox session."""

    session_id: str
    created_at: datetime
    last_activity_at: datetime
    command_count: int


SandboxFactory = Callable[[str, Path], DockerSandbox]
Clock = Callable[[], datetime]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class SandboxSessionManager:
    """Create, use, expire, and destroy persistent sandbox sessions."""

    def __init__(
        self,
        *,
        workspace_root: Path = Path(".sandbox-sessions"),
        idle_timeout: timedelta = timedelta(minutes=30),
        policy: CommandPolicy | None = None,
        sandbox_factory: SandboxFactory | None = None,
        clock: Clock = _utc_now,
    ) -> None:
        if idle_timeout.total_seconds() <= 0:
            raise ValueError("idle_timeout must be greater than zero")

        self.workspace_root = workspace_root.expanduser().resolve()
        self.idle_timeout = idle_timeout
        self.policy = policy or CommandPolicy()
        self._sandbox_factory = sandbox_factory or self._default_sandbox_factory
        self._clock = clock
        self._sessions: dict[str, SandboxSession] = {}
        self._lock = threading.RLock()

    def create_session(self) -> SessionSnapshot:
        """Create and register a new running sandbox."""
        session_id = uuid.uuid4().hex[:12]
        workspace = self.workspace_root / session_id
        sandbox = self._sandbox_factory(session_id, workspace)
        sandbox.create()
        now = self._clock()
        session = SandboxSession(
            session_id=session_id,
            sandbox=sandbox,
            created_at=now,
            last_activity_at=now,
        )
        with self._lock:
            self._sessions[session_id] = session
        return self._snapshot(session)

    def execute(
        self,
        session_id: str,
        command: list[str],
        *,
        timeout_seconds: float = 30.0,
    ) -> CommandResult:
        """Validate and run a command in an existing session."""
        validated = self.policy.validate(command, timeout_seconds)
        session = self._get_session(session_id)
        with session.lock:
            result = session.sandbox.execute(
                validated,
                timeout_seconds=timeout_seconds,
            )
            session.command_count += 1
            session.last_activity_at = self._clock()
            return result

    def get_session(self, session_id: str) -> SessionSnapshot:
        """Return current session metadata."""
        return self._snapshot(self._get_session(session_id))

    def import_metadata_archive(
        self,
        session_id: str,
        zip_bytes: bytes,
    ) -> ExtractedArchive:
        """Extract a Salesforce ZIP into the session's shared workspace."""
        session = self._get_session(session_id)
        with session.lock:
            result = extract_zip_to_directory(
                zip_bytes,
                session.sandbox.workspace / "metadata",
            )
            session.last_activity_at = self._clock()
            return result

    def get_workspace(self, session_id: str) -> Path:
        """Return a session workspace for trusted application services."""
        return self._get_session(session_id).sandbox.workspace

    def destroy_session(self, session_id: str) -> None:
        """Unregister and destroy a session."""
        with self._lock:
            session = self._sessions.pop(session_id, None)
        if session is None:
            raise SessionNotFound(session_id)
        with session.lock:
            session.sandbox.destroy()

    def cleanup_expired(self) -> list[str]:
        """Destroy sessions idle for at least the configured timeout."""
        cutoff = self._clock() - self.idle_timeout
        with self._lock:
            expired_ids = [
                session_id
                for session_id, session in self._sessions.items()
                if session.last_activity_at <= cutoff
            ]

        destroyed: list[str] = []
        for session_id in expired_ids:
            try:
                self.destroy_session(session_id)
            except SessionNotFound:
                continue
            destroyed.append(session_id)
        return destroyed

    def shutdown(self) -> None:
        """Destroy every active session, continuing after individual failures."""
        with self._lock:
            session_ids = list(self._sessions)

        errors: list[str] = []
        for session_id in session_ids:
            try:
                self.destroy_session(session_id)
            except (SandboxError, OSError) as exc:
                errors.append(f"{session_id}: {exc}")
        if errors:
            raise SandboxError("Some sandboxes could not be destroyed: " + "; ".join(errors))

    @property
    def active_session_count(self) -> int:
        with self._lock:
            return len(self._sessions)

    @staticmethod
    def _snapshot(session: SandboxSession) -> SessionSnapshot:
        return SessionSnapshot(
            session_id=session.session_id,
            created_at=session.created_at,
            last_activity_at=session.last_activity_at,
            command_count=session.command_count,
        )

    def _get_session(self, session_id: str) -> SandboxSession:
        with self._lock:
            session = self._sessions.get(session_id)
        if session is None:
            raise SessionNotFound(session_id)
        return session

    @staticmethod
    def _default_sandbox_factory(session_id: str, workspace: Path) -> DockerSandbox:
        return DockerSandbox(session_id=session_id, workspace=workspace)
