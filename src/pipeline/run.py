"""Orchestrate metadata retrieval, sandbox import, and parsing."""

import logging
from dataclasses import dataclass
from pathlib import Path

from src.auth.models import TokenPayload
from src.config.settings import get_settings
from src.knowledge_graph.builder import build_knowledge_graph
from src.knowledge_graph.models import GraphSummary
from src.knowledge_graph.repository import SQLiteGraphRepository
from src.metadata_api.client import retrieve
from src.metadata_api.zip_extractor import ExtractedArchive
from src.metadata_parser.models import ParseResult
from src.metadata_parser.service import parse_metadata_workspace
from src.sandbox.manager import SandboxSessionManager, SessionSnapshot

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class IngestionResult:
    """Artifacts produced by one complete Salesforce metadata ingestion."""

    session: SessionSnapshot
    archive: ExtractedArchive
    parsed: ParseResult
    parsed_output_path: Path
    graph: GraphSummary
    graph_database_path: Path


def run_after_auth(tokens: TokenPayload) -> bytes:
    """Run initial metadata retrieve using tokens. Returns ZIP bytes."""
    settings = get_settings()
    logger.info("Starting initial retrieve (api_version=%s)", settings.sf_api_version)
    zip_bytes = retrieve(
        tokens,
        api_version=settings.sf_api_version,
        poll_interval=2.0,
    )
    logger.info("Initial retrieve completed (%s bytes)", len(zip_bytes))
    return zip_bytes


def ingest_metadata_archive(
    zip_bytes: bytes,
    manager: SandboxSessionManager,
) -> IngestionResult:
    """Create a sandbox session, import metadata, and save normalized JSON."""
    session = manager.create_session()
    try:
        archive = manager.import_metadata_archive(session.session_id, zip_bytes)
        workspace = manager.get_workspace(session.session_id)
        parsed_output_path = workspace / "analysis" / "parsed_metadata.json"
        parsed = parse_metadata_workspace(
            archive.destination,
            output_path=parsed_output_path,
        )
        graph_database_path = workspace / "analysis" / "knowledge_graph.db"
        graph_repository = SQLiteGraphRepository(graph_database_path)
        graph = graph_repository.replace_graph(build_knowledge_graph(parsed))
    except Exception:
        try:
            manager.destroy_session(session.session_id)
        except Exception:
            logger.exception(
                "Could not clean up failed metadata session %s",
                session.session_id,
            )
        raise

    logger.info(
        "Metadata session %s prepared: %s files, %s graph nodes, %s graph edges",
        session.session_id,
        archive.file_count,
        graph.node_count,
        graph.edge_count,
    )
    return IngestionResult(
        session=manager.get_session(session.session_id),
        archive=archive,
        parsed=parsed,
        parsed_output_path=parsed_output_path,
        graph=graph,
        graph_database_path=graph_database_path,
    )


def run_ingestion_after_auth(
    tokens: TokenPayload,
    manager: SandboxSessionManager,
) -> IngestionResult:
    """Retrieve Salesforce metadata and prepare its sandbox workspace."""
    return ingest_metadata_archive(run_after_auth(tokens), manager)
