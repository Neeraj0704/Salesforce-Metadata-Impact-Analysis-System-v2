"""OAuth and callback routes."""

import logging
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import RedirectResponse
from starlette.concurrency import run_in_threadpool

from src.api.dependencies import get_graph_repository_factory, get_sandbox_manager
from src.auth.oauth import exchange_code_for_tokens, get_authorization_url
from src.pipeline.run import run_ingestion_after_auth
from src.knowledge_graph.factory import GraphRepositoryFactory
from src.sandbox.manager import SandboxSessionManager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

# In-memory store for CSRF state (MVP). Use proper session/redis in production.
_oauth_state: dict[str, Any] = {}


@router.get("/salesforce")
async def auth_salesforce() -> RedirectResponse:
    """Redirect to Salesforce OAuth authorize URL (with PKCE)."""
    url, state, code_verifier = get_authorization_url()
    _oauth_state["state"] = state
    _oauth_state["code_verifier"] = code_verifier
    return RedirectResponse(url=url, status_code=302)


@router.get("/callback")
async def auth_callback(
    request: Request,
    code: str | None = Query(None, alias="code", description="OAuth authorization code"),
    state: str | None = Query(None, alias="state", description="CSRF state token"),
    manager: SandboxSessionManager = Depends(get_sandbox_manager),
    graph_repository_factory: GraphRepositoryFactory = Depends(
        get_graph_repository_factory
    ),
) -> RedirectResponse:
    """Exchange the OAuth code, retrieve metadata, and prepare its sandbox."""
    if not code:
        logger.warning("Callback missing code")
        return RedirectResponse(url="/?error=missing_code", status_code=302)
    saved = _oauth_state.get("state")
    if saved and state != saved:
        logger.warning("State mismatch; possible CSRF")
        return RedirectResponse(url="/?error=invalid_state", status_code=302)
    code_verifier = _oauth_state.get("code_verifier")
    if not code_verifier:
        logger.warning("Missing code_verifier; PKCE required")
        return RedirectResponse(url="/?error=missing_code_verifier", status_code=302)
    try:
        tokens = await run_in_threadpool(exchange_code_for_tokens, code, code_verifier)
        ingestion = await run_in_threadpool(
            run_ingestion_after_auth,
            tokens,
            manager,
            graph_repository_factory,
        )
    except Exception as e:
        logger.exception("Auth or retrieve failed: %s", e)
        return RedirectResponse(url=f"/?error=auth_failed", status_code=302)
    return RedirectResponse(
        url=(
            "/?success=1&retrieved=1"
            f"&session_id={ingestion.session.session_id}"
            f"&files={ingestion.archive.file_count}"
            f"&components={ingestion.parsed.component_count}"
            f"&graph_nodes={ingestion.graph.node_count}"
            f"&graph_edges={ingestion.graph.edge_count}"
        ),
        status_code=302,
    )
