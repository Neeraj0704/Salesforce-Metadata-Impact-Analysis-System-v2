"""Lightweight dependency extraction for Apex source files."""

from __future__ import annotations

import re
from pathlib import Path

from src.metadata_parser.models import MetadataComponent, MetadataReference


_SOQL_OBJECT_PATTERN = re.compile(
    r"\b(?:FROM|UPDATE|INTO)\s+([A-Za-z][A-Za-z0-9_]*(?:__c|__mdt|__e)?)\b",
    re.IGNORECASE,
)
_CUSTOM_OBJECT_DECLARATION_PATTERN = re.compile(
    r"\b([A-Za-z][A-Za-z0-9_]*(?:__c|__mdt|__e))\s+[a-z][A-Za-z0-9_]*\b"
)
_CUSTOM_OBJECT_CONSTRUCTION_PATTERN = re.compile(
    r"\bnew\s+([A-Za-z][A-Za-z0-9_]*(?:__c|__mdt|__e))\b",
    re.IGNORECASE,
)
_SCHEMA_OBJECT_PATTERN = re.compile(
    r"\bSchema\.SObjectType\.([A-Za-z][A-Za-z0-9_]*)\b",
    re.IGNORECASE,
)
_TRIGGER_PATTERN = re.compile(
    r"\btrigger\s+([A-Za-z][A-Za-z0-9_]*)\s+on\s+([A-Za-z][A-Za-z0-9_]*)",
    re.IGNORECASE,
)


def parse_apex_source(
    path: Path,
    metadata_root: Path,
) -> tuple[list[MetadataComponent], list[MetadataReference]]:
    """Parse an Apex class or trigger and discover object references."""
    source = path.read_text(encoding="utf-8")
    source_path = path.relative_to(metadata_root).as_posix()
    is_trigger = path.suffix.lower() == ".trigger"
    component_type = "ApexTrigger" if is_trigger else "ApexClass"
    component_name = path.stem
    component_key = f"{component_type}:{component_name}"
    attributes: dict[str, str] = {}
    references: list[MetadataReference] = []

    object_names = set(_SOQL_OBJECT_PATTERN.findall(source))
    object_names.update(_CUSTOM_OBJECT_DECLARATION_PATTERN.findall(source))
    object_names.update(_CUSTOM_OBJECT_CONSTRUCTION_PATTERN.findall(source))
    object_names.update(_SCHEMA_OBJECT_PATTERN.findall(source))

    if is_trigger:
        trigger_match = _TRIGGER_PATTERN.search(source)
        if trigger_match:
            component_name = trigger_match.group(1)
            component_key = f"ApexTrigger:{component_name}"
            trigger_object = trigger_match.group(2)
            attributes["trigger_object"] = trigger_object
            references.append(
                MetadataReference(
                    source_key=component_key,
                    target_key=f"CustomObject:{trigger_object}",
                    relationship="TRIGGERS_ON",
                    source_path=source_path,
                    evidence=trigger_match.group(0),
                )
            )

    component = MetadataComponent(
        key=component_key,
        component_type=component_type,
        name=component_name,
        source_path=source_path,
        attributes=attributes,
    )
    existing_targets = {reference.target_key for reference in references}
    for object_name in sorted(object_names):
        target_key = f"CustomObject:{object_name}"
        if target_key in existing_targets:
            continue
        references.append(
            MetadataReference(
                source_key=component_key,
                target_key=target_key,
                relationship="REFERENCES_OBJECT",
                source_path=source_path,
                evidence=object_name,
            )
        )

    return [component], references
