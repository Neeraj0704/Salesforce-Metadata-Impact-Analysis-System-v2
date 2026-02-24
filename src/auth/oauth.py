"""Salesforce OAuth 2.0 Web Server flow with PKCE."""

import base64
import hashlib
import logging
import secrets
from urllib.parse import urlencode

import httpx

from src.auth.models import TokenPayload
from src.config.settings import get_settings

logger = logging.getLogger(__name__)


def _generate_code_verifier() -> str:
    """Generate a cryptographically random code_verifier (43-128 chars, [A-Za-z0-9-._~])."""
    return secrets.token_urlsafe(64)[:128]


def _compute_code_challenge(verifier: str) -> str:
    """Compute S256 code_challenge: BASE64URL(SHA256(verifier))."""
    digest = hashlib.sha256(verifier.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("utf-8")


def get_authorization_url(state: str | None = None) -> tuple[str, str, str]:
    """Build Salesforce OAuth authorize URL with PKCE.

    Returns:
        (authorize_url, state, code_verifier).
        Store state and code_verifier in session; pass code_verifier to exchange_code_for_tokens.
    """
    settings = get_settings()
    state = state or secrets.token_urlsafe(32)
    code_verifier = _generate_code_verifier()
    code_challenge = _compute_code_challenge(code_verifier)

    base = f"https://{settings.sf_login_domain}.salesforce.com/services/oauth2/authorize"
    params = {
        "response_type": "code",
        "client_id": settings.sf_client_id,
        "redirect_uri": settings.sf_redirect_uri,
        "scope": "api refresh_token offline_access",
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    url = f"{base}?{urlencode(params)}"
    logger.debug("Built OAuth authorize URL (state=%s...)", state[:8] if len(state) >= 8 else state)
    return url, state, code_verifier


def exchange_code_for_tokens(code: str, code_verifier: str) -> TokenPayload:
    """Exchange authorization code for tokens. Requires code_verifier for PKCE.

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
        "code_verifier": code_verifier,
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