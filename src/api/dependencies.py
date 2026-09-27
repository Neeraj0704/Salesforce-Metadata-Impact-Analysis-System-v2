"""Shared application dependencies."""

from datetime import timedelta

from src.sandbox.manager import SandboxSessionManager


_sandbox_manager = SandboxSessionManager(idle_timeout=timedelta(minutes=30))


def get_sandbox_manager() -> SandboxSessionManager:
    """Return the process-wide sandbox session manager."""
    return _sandbox_manager
