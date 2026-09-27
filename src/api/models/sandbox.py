"""Schemas for the sandbox session API."""

from datetime import datetime

from pydantic import BaseModel, Field


class SandboxSessionResponse(BaseModel):
    session_id: str
    created_at: datetime
    last_activity_at: datetime
    command_count: int


class SandboxCommandRequest(BaseModel):
    program: str = Field(..., min_length=1, max_length=100)
    arguments: list[str] = Field(default_factory=list, max_length=100)
    timeout_seconds: float = Field(default=30.0, gt=0, le=60)


class SandboxCommandResponse(BaseModel):
    exit_code: int
    succeeded: bool
    stdout: str
    stderr: str


class SandboxDeleteResponse(BaseModel):
    session_id: str
    destroyed: bool
