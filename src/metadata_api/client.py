"""Metadata API REST client: create retrieve job, poll, fetch ZIP."""

import base64
import logging
import time

import httpx

from src.auth.models import TokenPayload
from src.metadata_api.models import RetrieveRequest, RetrieveResultResponse, RetrieveStatusResponse
from src.metadata_api.package import build_initial_retrieve_request

logger = logging.getLogger(__name__)

DEFAULT_POLL_INTERVAL_SEC = 2.0
MAX_POLL_ATTEMPTS = 600  # ~20 min at 2s


def _base_url(tokens: TokenPayload, api_version: str) -> str:
    base = str(tokens.instance_url).rstrip("/")
    return f"{base}/services/data/v{api_version}/metadata"


def create_retrieve_job(
    tokens: TokenPayload,
    api_version: str,
    request_body: RetrieveRequest | None = None,
) -> str:
    """Create async retrieve job. Returns job id."""
    url = f"{_base_url(tokens, api_version)}/retrieve"
    body = (request_body or build_initial_retrieve_request(api_version)).model_dump(by_alias=True, exclude_none=True)
    headers = {
        "Authorization": f"Bearer {tokens.access_token}",
        "Content-Type": "application/json",
    }
    try:
        resp = httpx.post(url, json=body, headers=headers, timeout=60.0)
        resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        logger.exception("Create retrieve job failed: %s %s", e.response.status_code, e.response.text)
        raise
    data = resp.json()
    job_id = data.get("id")
    if not job_id:
        raise ValueError("Retrieve response missing 'id'")
    logger.info("Retrieve job created: %s", job_id)
    return job_id


def check_retrieve_status(
    tokens: TokenPayload,
    job_id: str,
    api_version: str,
) -> RetrieveStatusResponse:
    """Poll retrieve job status. Returns parsed RetrieveStatusResponse."""
    url = f"{_base_url(tokens, api_version)}/retrieve/{job_id}"
    headers = {"Authorization": f"Bearer {tokens.access_token}"}
    try:
        resp = httpx.get(url, headers=headers, timeout=30.0)
        resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        logger.exception("Check retrieve status failed: %s %s", e.response.status_code, e.response.text)
        raise
    return RetrieveStatusResponse.model_validate(resp.json())


def get_retrieve_result(
    tokens: TokenPayload,
    job_id: str,
    api_version: str,
) -> bytes:
    """Fetch result ZIP (base64) and return decoded bytes."""
    url = f"{_base_url(tokens, api_version)}/retrieve/{job_id}"
    params = {"includeZip": "true"}
    headers = {"Authorization": f"Bearer {tokens.access_token}"}
    try:
        resp = httpx.get(url, params=params, headers=headers, timeout=120.0)
        resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        logger.exception("Get retrieve result failed: %s %s", e.response.status_code, e.response.text)
        raise
    result = RetrieveResultResponse.model_validate(resp.json())
    if not result.zip_file:
        raise ValueError("Retrieve result missing 'zipFile'")
    return base64.b64decode(result.zip_file)


def retrieve(
    tokens: TokenPayload,
    api_version: str = "59.0",
    poll_interval: float = DEFAULT_POLL_INTERVAL_SEC,
    request_body: RetrieveRequest | None = None,
) -> bytes:
    """Run retrieve: create job → poll until done → return ZIP bytes."""
    job_id = create_retrieve_job(tokens, api_version, request_body)
    attempts = 0
    while attempts < MAX_POLL_ATTEMPTS:
        status_resp = check_retrieve_status(tokens, job_id, api_version)
        if status_resp.status == "Succeeded":
            logger.info("Retrieve job %s succeeded", job_id)
            return get_retrieve_result(tokens, job_id, api_version)
        if status_resp.status == "Failed":
            error_msg = status_resp.error_message or "Unknown error"
            raise RuntimeError(f"Metadata retrieve job {job_id} failed: {error_msg}")
        attempts += 1
        time.sleep(poll_interval)
    raise RuntimeError(f"Retrieve job {job_id} timed out after {MAX_POLL_ATTEMPTS} polls")