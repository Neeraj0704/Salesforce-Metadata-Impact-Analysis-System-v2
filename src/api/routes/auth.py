"""OAuth and callback routes."""

import logging
from typing import Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import RedirectResponse

from src.auth.oauth import exchange_code_for_tokens, get_authorization_url
from src.pipeline.run import run_after_auth

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

# In-memory store for CSRF state (MVP). Use proper session/redis in production.
_oauth_state: dict[str, Any] = {}


@router.get("/salesforce")
async def auth_salesforce() -> RedirectResponse:
    """Redirect to Salesforce OAuth authorize URL."""
    url, state = get_authorization_url()
    _oauth_state["state"] = state
    return RedirectResponse(url=url, status_code=302)


@router.get("/callback")
async def auth_callback(
    request: Request,
    code: str | None = Query(None, alias="code", description="OAuth authorization code"),
    state: str | None = Query(None, alias="state", description="CSRF state token"),
) -> RedirectResponse:
    """Handle OAuth callback: exchange code → tokens → initial retrieve → redirect."""
    if not code:
        logger.warning("Callback missing code")
        return RedirectResponse(url="/?error=missing_code", status_code=302)
    saved = _oauth_state.get("state")
    if saved and state != saved:
        logger.warning("State mismatch; possible CSRF")
        return RedirectResponse(url="/?error=invalid_state", status_code=302)
    try:
        tokens = exchange_code_for_tokens(code)
        zip_bytes = run_after_auth(tokens)
    except Exception as e:
        logger.exception("Auth or retrieve failed: %s", e)
        return RedirectResponse(url=f"/?error=auth_failed", status_code=302)
    # TODO: persist zip_bytes or tokens per session; for now just signal success
    return RedirectResponse(url="/?success=1&retrieved=1", status_code=302)