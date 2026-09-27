"""HTTP endpoints for persistent Docker sandbox sessions."""

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from starlette.concurrency import run_in_threadpool

from src.api.dependencies import get_sandbox_manager
from src.api.models.sandbox import (
    SandboxCommandRequest,
    SandboxCommandResponse,
    SandboxDeleteResponse,
    SandboxSessionResponse,
)
from src.metadata_parser.models import ParseResult
from src.sandbox.controller import SandboxError
from src.sandbox.manager import SandboxSessionManager, SessionNotFound, SessionSnapshot
from src.sandbox.policy import CommandRejected


router = APIRouter(prefix="/sandbox/sessions", tags=["sandbox"])


def _session_response(snapshot: SessionSnapshot) -> SandboxSessionResponse:
    return SandboxSessionResponse(
        session_id=snapshot.session_id,
        created_at=snapshot.created_at,
        last_activity_at=snapshot.last_activity_at,
        command_count=snapshot.command_count,
    )


def _load_parse_result(output_path: str) -> ParseResult:
    return ParseResult.model_validate_json(
        Path(output_path).read_text(encoding="utf-8")
    )


@router.post("", response_model=SandboxSessionResponse, status_code=status.HTTP_201_CREATED)
async def create_sandbox_session(
    manager: SandboxSessionManager = Depends(get_sandbox_manager),
) -> SandboxSessionResponse:
    """Start one persistent sandbox container."""
    try:
        snapshot = await run_in_threadpool(manager.create_session)
    except SandboxError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return _session_response(snapshot)


@router.get("/{session_id}", response_model=SandboxSessionResponse)
async def get_sandbox_session(
    session_id: str,
    manager: SandboxSessionManager = Depends(get_sandbox_manager),
) -> SandboxSessionResponse:
    """Return lifecycle information for one sandbox session."""
    try:
        snapshot = manager.get_session(session_id)
    except SessionNotFound as exc:
        raise HTTPException(status_code=404, detail="Sandbox session not found") from exc
    return _session_response(snapshot)


@router.get("/{session_id}/metadata", response_model=ParseResult)
async def get_parsed_metadata(
    session_id: str,
    manager: SandboxSessionManager = Depends(get_sandbox_manager),
) -> ParseResult:
    """Return normalized metadata produced during Salesforce ingestion."""
    try:
        output_path = manager.get_workspace(session_id) / "analysis/parsed_metadata.json"
    except SessionNotFound as exc:
        raise HTTPException(status_code=404, detail="Sandbox session not found") from exc
    if not output_path.is_file():
        raise HTTPException(status_code=404, detail="Session has no parsed metadata")
    try:
        return await run_in_threadpool(_load_parse_result, str(output_path))
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=500, detail="Parsed metadata is unreadable") from exc


@router.post("/{session_id}/commands", response_model=SandboxCommandResponse)
async def run_sandbox_command(
    session_id: str,
    request: SandboxCommandRequest,
    manager: SandboxSessionManager = Depends(get_sandbox_manager),
) -> SandboxCommandResponse:
    """Run one approved command in an existing sandbox session."""
    try:
        result = await run_in_threadpool(
            manager.execute,
            session_id,
            [request.program, *request.arguments],
            timeout_seconds=request.timeout_seconds,
        )
    except SessionNotFound as exc:
        raise HTTPException(status_code=404, detail="Sandbox session not found") from exc
    except CommandRejected as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except SandboxError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return SandboxCommandResponse(
        exit_code=result.exit_code,
        succeeded=result.succeeded,
        stdout=result.stdout,
        stderr=result.stderr,
    )


@router.delete("/{session_id}", response_model=SandboxDeleteResponse)
async def destroy_sandbox_session(
    session_id: str,
    manager: SandboxSessionManager = Depends(get_sandbox_manager),
) -> SandboxDeleteResponse:
    """Destroy a sandbox container and delete its workspace."""
    try:
        await run_in_threadpool(manager.destroy_session, session_id)
    except SessionNotFound as exc:
        raise HTTPException(status_code=404, detail="Sandbox session not found") from exc
    except SandboxError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return SandboxDeleteResponse(session_id=session_id, destroyed=True)
