"""Discover metadata files, run parsers, and persist normalized output."""

from __future__ import annotations

import json
import logging
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Callable

from src.metadata_parser.apex import parse_apex_source
from src.metadata_parser.models import MetadataComponent, MetadataReference, ParseResult
from src.metadata_parser.xml_metadata import (
    parse_custom_object,
    parse_flow,
    parse_permission_set,
)


logger = logging.getLogger(__name__)
Parser = Callable[
    [Path, Path],
    tuple[list[MetadataComponent], list[MetadataReference]],
]


def _parser_for(path: Path) -> Parser | None:
    name = path.name.lower()
    if name.endswith((".object", ".object-meta.xml")):
        return parse_custom_object
    if name.endswith((".flow", ".flow-meta.xml")):
        return parse_flow
    if name.endswith((".permissionset", ".permissionset-meta.xml")):
        return parse_permission_set
    if name.endswith((".cls", ".trigger")):
        return parse_apex_source
    return None


def parse_metadata_workspace(
    metadata_root: Path,
    *,
    output_path: Path | None = None,
) -> ParseResult:
    """Parse supported metadata recursively and optionally save JSON output."""
    metadata_root = metadata_root.expanduser().resolve()
    if not metadata_root.is_dir():
        raise FileNotFoundError(f"Metadata directory does not exist: {metadata_root}")

    components: dict[str, MetadataComponent] = {}
    references: dict[tuple[str, str, str, str], MetadataReference] = {}
    warnings: list[str] = []

    for path in sorted(metadata_root.rglob("*")):
        if not path.is_file():
            continue
        parser = _parser_for(path)
        if parser is None:
            continue
        try:
            parsed_components, parsed_references = parser(path, metadata_root)
        except (ET.ParseError, UnicodeDecodeError, OSError, ValueError) as exc:
            relative_path = path.relative_to(metadata_root).as_posix()
            warning = f"Could not parse {relative_path}: {exc}"
            logger.warning(warning)
            warnings.append(warning)
            continue

        for component in parsed_components:
            components[component.key] = component
        for reference in parsed_references:
            key = (
                reference.source_key,
                reference.target_key,
                reference.relationship,
                reference.source_path,
            )
            references[key] = reference

    result = ParseResult(
        components=sorted(components.values(), key=lambda item: item.key),
        references=sorted(
            references.values(),
            key=lambda item: (
                item.source_key,
                item.relationship,
                item.target_key,
                item.source_path,
            ),
        ),
        warnings=warnings,
    )

    if output_path is not None:
        output_path = output_path.expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(result.model_dump(mode="json"), indent=2, sort_keys=True),
            encoding="utf-8",
        )

    return result
