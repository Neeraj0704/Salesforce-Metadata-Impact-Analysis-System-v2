"""Schemas for the sandbox session API."""

from datetime import datetime

from pydantic import BaseModel, Field

from src.impact_analysis.models import ChangeType


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


class ImpactAnalysisRequest(BaseModel):
    component_key: str = Field(..., min_length=3, max_length=500)
    change_type: ChangeType = "modify"
    max_depth: int = Field(default=5, ge=1, le=10)
