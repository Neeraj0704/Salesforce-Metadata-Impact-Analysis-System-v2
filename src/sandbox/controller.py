"""Manage a Docker container that persists for one agent session."""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


DEFAULT_IMAGE = "salesforce-agent-sandbox:latest"
_SESSION_ID_PATTERN = re.compile(r"^[a-f0-9]{12}$")


class SandboxError(RuntimeError):
    """Raised when a sandbox lifecycle operation fails."""


@dataclass(frozen=True)
class CommandResult:
    """Result returned by a command executed inside the sandbox."""

    exit_code: int
    stdout: str
    stderr: str

    @property
    def succeeded(self) -> bool:
        return self.exit_code == 0


class DockerSandbox:
    """A persistent, isolated Docker container for one agent session."""

    def __init__(
        self,
        *,
        image: str = DEFAULT_IMAGE,
        session_id: str | None = None,
        workspace: Path | None = None,
    ) -> None:
        self.image = image
        self.session_id = session_id or uuid.uuid4().hex[:12]
        if not _SESSION_ID_PATTERN.fullmatch(self.session_id):
            raise ValueError("session_id must contain exactly 12 lowercase hex characters")

        self.container_name = f"agent-sandbox-{self.session_id}"
        self.workspace = workspace or Path(
            tempfile.mkdtemp(prefix=f"agent-sandbox-{self.session_id}-")
        )
        self.workspace = self.workspace.expanduser().resolve()
        self._created = False

    @staticmethod
    def build_image(
        *,
        image: str = DEFAULT_IMAGE,
        dockerfile_directory: Path = Path("sandbox"),
    ) -> None:
        """Build the sandbox image."""
        DockerSandbox._run_host_command(
            ["docker", "build", "--tag", image, str(dockerfile_directory)],
            operation="build sandbox image",
        )

    def create(self) -> None:
        """Create the session container and leave it running."""
        if self._created:
            raise SandboxError("Sandbox session has already been created")

        self.workspace.mkdir(parents=True, exist_ok=True)
        self.workspace.chmod(0o777)
        command = [
            "docker",
            "run",
            "--detach",
            "--name",
            self.container_name,
            "--hostname",
            "sandbox",
            "--network",
            "none",
            "--memory",
            "512m",
            "--cpus",
            "1.0",
            "--pids-limit",
            "128",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--read-only",
            "--tmpfs",
            "/tmp:rw,noexec,nosuid,size=64m",
            "--mount",
            f"type=bind,src={self.workspace},dst=/workspace",
            "--workdir",
            "/workspace",
            self.image,
        ]
        self._run_host_command(command, operation="create sandbox session")
        self._created = True

    def execute(
        self,
        command: Sequence[str],
        *,
        timeout_seconds: float = 30.0,
        max_output_chars: int = 50_000,
    ) -> CommandResult:
        """Execute one argument-vector command in the active container."""
        if not self._created:
            raise SandboxError("Sandbox session has not been created")
        if not command or any(not isinstance(part, str) or "\x00" in part for part in command):
            raise ValueError("command must be a non-empty sequence of valid strings")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than zero")

        try:
            completed = subprocess.run(
                [
                    "docker",
                    "exec",
                    self.container_name,
                    "timeout",
                    "--signal=KILL",
                    f"{timeout_seconds:g}s",
                    *command,
                ],
                capture_output=True,
                text=True,
                timeout=timeout_seconds + 5,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise SandboxError(
                "Docker did not return after the sandbox command timeout"
            ) from exc

        return CommandResult(
            exit_code=completed.returncode,
            stdout=completed.stdout[-max_output_chars:],
            stderr=completed.stderr[-max_output_chars:],
        )

    def destroy(self, *, remove_workspace: bool = True) -> None:
        """Force-remove the container and optionally delete its workspace."""
        if self._created:
            completed = subprocess.run(
                ["docker", "rm", "--force", self.container_name],
                capture_output=True,
                text=True,
                check=False,
            )
            if completed.returncode != 0 and "No such container" not in completed.stderr:
                raise SandboxError(f"Could not destroy sandbox: {completed.stderr.strip()}")
            self._created = False

        if remove_workspace and self.workspace.exists():
            shutil.rmtree(self.workspace)

    def __enter__(self) -> DockerSandbox:
        self.create()
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.destroy()

    @staticmethod
    def _run_host_command(command: list[str], *, operation: str) -> None:
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=False,
            )
        except FileNotFoundError as exc:
            raise SandboxError("Docker is not installed or is not on PATH") from exc

        if completed.returncode != 0:
            details = completed.stderr.strip() or completed.stdout.strip()
            raise SandboxError(f"Could not {operation}: {details}")
