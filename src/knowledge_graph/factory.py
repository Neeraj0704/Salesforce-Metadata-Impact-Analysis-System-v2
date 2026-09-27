"""Construct the configured production graph repository."""

from __future__ import annotations

from typing import Callable

from src.config.settings import get_settings
from src.knowledge_graph.neo4j_repository import Neo4jGraphRepository
from src.knowledge_graph.repository import GraphRepository


GraphRepositoryFactory = Callable[[str], GraphRepository]


def create_graph_repository(session_id: str) -> Neo4jGraphRepository:
    settings = get_settings()
    if settings.neo4j_mode == "local":
        uri = settings.neo4j_local_uri
        user = settings.neo4j_local_user
        password = settings.neo4j_local_password
    else:
        if not settings.neo4j_uri or not settings.neo4j_username or not settings.neo4j_password:
            raise ValueError(
                "Remote Neo4j requires NEO4J_URI, NEO4J_USERNAME, and NEO4J_PASSWORD"
            )
        uri = settings.neo4j_uri
        user = settings.neo4j_username
        password = settings.neo4j_password
    return Neo4jGraphRepository(
        uri=uri,
        user=user,
        password=password,
        database=settings.neo4j_database,
        session_id=session_id,
    )
