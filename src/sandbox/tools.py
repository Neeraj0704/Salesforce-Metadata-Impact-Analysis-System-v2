"""Agent-facing tool definitions backed by the sandbox session manager."""

from __future__ import annotations

from typing import Any

from src.impact_analysis.analyzer import analyze_impact
from src.impact_analysis.models import ChangeType
from src.knowledge_graph.repository import SQLiteGraphRepository
from src.sandbox.manager import SandboxSessionManager


RUN_COMMAND_TOOL: dict[str, Any] = {
    "type": "function",
    "name": "run_sandbox_command",
    "description": (
        "Run an approved command in the current isolated sandbox session. "
        "Files in /workspace persist until the session ends."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "program": {
                "type": "string",
                "description": "Approved executable name, such as python, rg, or cat.",
            },
            "arguments": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Arguments passed directly to the executable without a shell.",
            },
            "timeout_seconds": {
                "type": "number",
                "minimum": 0.1,
                "maximum": 60,
                "default": 30,
            },
        },
        "required": ["program", "arguments"],
        "additionalProperties": False,
    },
}

ANALYZE_IMPACT_TOOL: dict[str, Any] = {
    "type": "function",
    "name": "analyze_metadata_impact",
    "description": (
        "Find Salesforce components affected by a proposed metadata change and "
        "return an explainable risk score."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "component_key": {
                "type": "string",
                "description": "Graph key such as CustomField:Account.Status__c.",
            },
            "change_type": {
                "type": "string",
                "enum": ["add", "modify", "delete"],
                "default": "modify",
            },
            "max_depth": {
                "type": "integer",
                "minimum": 1,
                "maximum": 10,
                "default": 5,
            },
        },
        "required": ["component_key"],
        "additionalProperties": False,
    },
}

AGENT_TOOLS = [RUN_COMMAND_TOOL, ANALYZE_IMPACT_TOOL]


class SandboxToolAdapter:
    """Bind an agent tool call to one already-created sandbox session."""

    def __init__(self, manager: SandboxSessionManager, session_id: str) -> None:
        self.manager = manager
        self.session_id = session_id

    def run_sandbox_command(
        self,
        *,
        program: str,
        arguments: list[str],
        timeout_seconds: float = 30.0,
    ) -> dict[str, Any]:
        result = self.manager.execute(
            self.session_id,
            [program, *arguments],
            timeout_seconds=timeout_seconds,
        )
        return {
            "exit_code": result.exit_code,
            "succeeded": result.succeeded,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }

    def analyze_metadata_impact(
        self,
        *,
        component_key: str,
        change_type: ChangeType = "modify",
        max_depth: int = 5,
    ) -> dict[str, Any]:
        workspace = self.manager.get_workspace(self.session_id)
        repository = SQLiteGraphRepository(
            workspace / "analysis" / "knowledge_graph.db"
        )
        report = analyze_impact(
            repository,
            component_key,
            change_type=change_type,
            max_depth=max_depth,
        )
        return report.model_dump(mode="json")
