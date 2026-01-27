"""Salesforce OAuth 2.0 Web Server flow: authorize URL and code exchange."""

import logging
import secrets
from urllib.parse import urlencode

import httpx

from src.auth.models import TokenPayload
from src.config.settings import get_settings

logger = logging.getLogger(__name__)


def get_authorization_url(state: str | None = None) -> tuple[str, str]:
    """Build Salesforce OAuth authorize URL and CSRF state.

    Returns:
        (authorize_url, state). Persist state in session; verify in callback.
    """
    settings = get_settings()
    state = state or secrets.token_urlsafe(32)
    base = f"https://{settings.sf_login_domain}.salesforce.com/services/oauth2/authorize"
    params = {
        "response_type": "code",
        "client_id": settings.sf_client_id,
        "redirect_uri": settings.sf_redirect_uri,
        "scope": "api refresh_token offline_access",
        "state": state,
    }
    url = f"{base}?{urlencode(params)}"
    logger.debug("Built OAuth authorize URL (state=%s...)", state[:8] if len(state) >= 8 else state)
    return url, state


def exchange_code_for_tokens(code: str) -> TokenPayload:
    """Exchange authorization code for access and refresh tokens.

    Raises:
        httpx.HTTPStatusError: On token endpoint error (e.g. invalid code).
        KeyError: If response missing required keys (access_token, etc.).
    """
    settings = get_settings()
    url = f"https://{settings.sf_login_domain}.salesforce.com/services/oauth2/token"
    data = {
        "grant_type": "authorization_code",
        "code": code.strip(),
        "client_id": settings.sf_client_id,
        "client_secret": settings.sf_client_secret,
        "redirect_uri": settings.sf_redirect_uri,
    }
    try:
        resp = httpx.post(url, data=data, timeout=30.0)
        resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        logger.exception("Token exchange failed: %s %s", e.response.status_code, e.response.text)
        raise
    body = resp.json()
    return TokenPayload(
        access_token=body["access_token"],
        refresh_token=body["refresh_token"],
        instance_url=body["instance_url"],
    )