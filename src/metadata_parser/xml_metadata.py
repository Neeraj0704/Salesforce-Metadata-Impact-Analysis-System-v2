"""Parsers for XML-based Salesforce metadata types."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from src.metadata_parser.models import MetadataComponent, MetadataReference


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _direct_text(element: ET.Element, name: str) -> str | None:
    for child in element:
        if _local_name(child.tag) == name and child.text:
            value = child.text.strip()
            if value:
                return value
    return None


def _direct_texts(element: ET.Element, name: str) -> list[str]:
    values: list[str] = []
    for child in element:
        if _local_name(child.tag) == name and child.text:
            value = child.text.strip()
            if value:
                values.append(value)
    return values


def _elements(root: ET.Element, name: str) -> list[ET.Element]:
    return [element for element in root.iter() if _local_name(element.tag) == name]


def _metadata_name(path: Path, suffixes: tuple[str, ...]) -> str:
    name = path.name
    for suffix in suffixes:
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return path.stem


def _relative_path(path: Path, metadata_root: Path) -> str:
    return path.relative_to(metadata_root).as_posix()


def parse_custom_object(
    path: Path,
    metadata_root: Path,
) -> tuple[list[MetadataComponent], list[MetadataReference]]:
    """Parse a CustomObject XML file and its nested fields."""
    root = ET.parse(path).getroot()
    source_path = _relative_path(path, metadata_root)
    object_name = _direct_text(root, "fullName") or _metadata_name(
        path, (".object-meta.xml", ".object")
    )
    object_key = f"CustomObject:{object_name}"
    components = [
        MetadataComponent(
            key=object_key,
            component_type="CustomObject",
            name=object_name,
            source_path=source_path,
            attributes={
                "label": _direct_text(root, "label"),
                "plural_label": _direct_text(root, "pluralLabel"),
                "sharing_model": _direct_text(root, "sharingModel"),
            },
        )
    ]
    references: list[MetadataReference] = []

    for field_element in _elements(root, "fields"):
        field_name = _direct_text(field_element, "fullName")
        if not field_name:
            continue
        qualified_name = f"{object_name}.{field_name}"
        field_key = f"CustomField:{qualified_name}"
        reference_targets = _direct_texts(field_element, "referenceTo")
        components.append(
            MetadataComponent(
                key=field_key,
                component_type="CustomField",
                name=qualified_name,
                source_path=source_path,
                attributes={
                    "label": _direct_text(field_element, "label"),
                    "field_type": _direct_text(field_element, "type"),
                    "required": _direct_text(field_element, "required") == "true",
                    "unique": _direct_text(field_element, "unique") == "true",
                    "external_id": _direct_text(field_element, "externalId") == "true",
                    "reference_to": reference_targets,
                },
            )
        )
        references.append(
            MetadataReference(
                source_key=object_key,
                target_key=field_key,
                relationship="HAS_FIELD",
                source_path=source_path,
                evidence=field_name,
            )
        )
        for target in reference_targets:
            references.append(
                MetadataReference(
                    source_key=field_key,
                    target_key=f"CustomObject:{target}",
                    relationship="REFERENCES_OBJECT",
                    source_path=source_path,
                    evidence=target,
                )
            )

    return components, references


def parse_flow(
    path: Path,
    metadata_root: Path,
) -> tuple[list[MetadataComponent], list[MetadataReference]]:
    """Parse object and field dependencies from a Flow XML file."""
    root = ET.parse(path).getroot()
    source_path = _relative_path(path, metadata_root)
    flow_name = _direct_text(root, "fullName") or _metadata_name(
        path, (".flow-meta.xml", ".flow")
    )
    flow_key = f"Flow:{flow_name}"
    component = MetadataComponent(
        key=flow_key,
        component_type="Flow",
        name=flow_name,
        source_path=source_path,
        attributes={
            "label": _direct_text(root, "label"),
            "status": _direct_text(root, "status"),
            "process_type": _direct_text(root, "processType"),
        },
    )

    object_names = {
        element.text.strip()
        for element in _elements(root, "object")
        if element.text and element.text.strip()
    }
    references: list[MetadataReference] = []
    for object_name in sorted(object_names):
        references.append(
            MetadataReference(
                source_key=flow_key,
                target_key=f"CustomObject:{object_name}",
                relationship="USES_OBJECT",
                source_path=source_path,
                evidence=object_name,
            )
        )

    field_names = {
        element.text.strip()
        for element in _elements(root, "field")
        if element.text and element.text.strip()
    }
    only_object = next(iter(object_names)) if len(object_names) == 1 else None
    for field_name in sorted(field_names):
        qualified_name = field_name if "." in field_name else None
        if qualified_name is None and only_object is not None:
            qualified_name = f"{only_object}.{field_name}"
        if qualified_name:
            references.append(
                MetadataReference(
                    source_key=flow_key,
                    target_key=f"CustomField:{qualified_name}",
                    relationship="USES_FIELD",
                    source_path=source_path,
                    evidence=field_name,
                )
            )

    return [component], references


def parse_permission_set(
    path: Path,
    metadata_root: Path,
) -> tuple[list[MetadataComponent], list[MetadataReference]]:
    """Parse object, field, Apex, and Flow access from a PermissionSet."""
    root = ET.parse(path).getroot()
    source_path = _relative_path(path, metadata_root)
    permission_name = _direct_text(root, "fullName") or _metadata_name(
        path, (".permissionset-meta.xml", ".permissionset")
    )
    permission_key = f"PermissionSet:{permission_name}"
    component = MetadataComponent(
        key=permission_key,
        component_type="PermissionSet",
        name=permission_name,
        source_path=source_path,
        attributes={"label": _direct_text(root, "label")},
    )
    references: list[MetadataReference] = []

    mappings = (
        ("object", "CustomObject", "GRANTS_OBJECT_ACCESS"),
        ("field", "CustomField", "GRANTS_FIELD_ACCESS"),
        ("apexClass", "ApexClass", "GRANTS_APEX_ACCESS"),
        ("flow", "Flow", "GRANTS_FLOW_ACCESS"),
    )
    for element_name, target_type, relationship in mappings:
        values = {
            element.text.strip()
            for element in _elements(root, element_name)
            if element.text and element.text.strip()
        }
        for value in sorted(values):
            references.append(
                MetadataReference(
                    source_key=permission_key,
                    target_key=f"{target_type}:{value}",
                    relationship=relationship,
                    source_path=source_path,
                    evidence=value,
                )
            )

    return [component], references
