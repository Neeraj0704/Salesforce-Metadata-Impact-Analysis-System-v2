"""Normalized output shared by every Salesforce metadata parser."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class MetadataComponent(BaseModel):
    """One Salesforce metadata component or nested component."""

    model_config = ConfigDict(frozen=True)

    key: str
    component_type: str
    name: str
    source_path: str
    attributes: dict[str, Any] = Field(default_factory=dict)


class MetadataReference(BaseModel):
    """A directed relationship discovered in metadata or source code."""

    model_config = ConfigDict(frozen=True)

    source_key: str
    target_key: str
    relationship: str
    source_path: str
    evidence: str | None = None


class ParseResult(BaseModel):
    """Complete normalized parser output for one metadata workspace."""

    components: list[MetadataComponent] = Field(default_factory=list)
    references: list[MetadataReference] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @property
    def component_count(self) -> int:
        return len(self.components)

    @property
    def reference_count(self) -> int:
        return len(self.references)
