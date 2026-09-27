"""Shared application dependencies."""

from datetime import timedelta

from src.knowledge_graph.factory import GraphRepositoryFactory, create_graph_repository
from src.sandbox.manager import SandboxSessionManager


def _delete_session_graph(session_id: str) -> None:
    repository = create_graph_repository(session_id)
    try:
        repository.clear_graph()
    finally:
        repository.close()


_sandbox_manager = SandboxSessionManager(
    idle_timeout=timedelta(minutes=30),
    session_cleanup=_delete_session_graph,
)


def get_sandbox_manager() -> SandboxSessionManager:
    """Return the process-wide sandbox session manager."""
    return _sandbox_manager


def get_graph_repository_factory() -> GraphRepositoryFactory:
    """Return the configured production graph repository factory."""
    return create_graph_repository
