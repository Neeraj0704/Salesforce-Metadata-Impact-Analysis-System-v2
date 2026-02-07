"""Orchestrate post-auth flow: initial Metadata API retrieve."""

import logging

from src.auth.models import TokenPayload
from src.metadata_api.client import retrieve
from src.config.settings import get_settings

logger = logging.getLogger(__name__)

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