"""Safely inspect and extract Salesforce metadata ZIP archives."""

from __future__ import annotations

import io
import logging
import shutil
import stat
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Iterator


logger = logging.getLogger(__name__)

DEFAULT_MAX_FILES = 20_000
DEFAULT_MAX_FILE_BYTES = 50 * 1024 * 1024
DEFAULT_MAX_TOTAL_BYTES = 500 * 1024 * 1024


class UnsafeArchiveError(ValueError):
    """Raised when an archive could escape or exhaust its workspace."""


@dataclass(frozen=True)
class ExtractedArchive:
    """Summary of files written from one metadata archive."""

    destination: Path
    file_count: int
    total_bytes: int
    paths: tuple[str, ...]


def _safe_relative_path(name: str) -> PurePosixPath | None:
    """Normalize a ZIP entry name and reject absolute or parent paths."""
    normalized = name.replace("\\", "/")
    path = PurePosixPath(normalized)
    if not normalized or normalized.endswith("/"):
        return None
    if path.is_absolute() or ".." in path.parts:
        raise UnsafeArchiveError(f"Unsafe archive path: {name}")
    if any(part in {"", "."} for part in path.parts):
        raise UnsafeArchiveError(f"Invalid archive path: {name}")
    return path


def _is_symlink(info: zipfile.ZipInfo) -> bool:
    unix_mode = info.external_attr >> 16
    return stat.S_ISLNK(unix_mode)


def _validated_files(
    archive: zipfile.ZipFile,
    *,
    max_files: int,
    max_file_bytes: int,
    max_total_bytes: int,
) -> list[tuple[zipfile.ZipInfo, PurePosixPath]]:
    files: list[tuple[zipfile.ZipInfo, PurePosixPath]] = []
    seen: set[str] = set()
    total_bytes = 0

    for info in archive.infolist():
        relative_path = _safe_relative_path(info.filename)
        if relative_path is None:
            continue
        if _is_symlink(info):
            raise UnsafeArchiveError(f"Symbolic links are not allowed: {info.filename}")
        if info.file_size > max_file_bytes:
            raise UnsafeArchiveError(f"Archive entry is too large: {info.filename}")

        normalized_name = relative_path.as_posix()
        if normalized_name in seen:
            raise UnsafeArchiveError(f"Duplicate archive path: {normalized_name}")
        seen.add(normalized_name)

        files.append((info, relative_path))
        if len(files) > max_files:
            raise UnsafeArchiveError(f"Archive contains more than {max_files} files")

        total_bytes += info.file_size
        if total_bytes > max_total_bytes:
            raise UnsafeArchiveError(
                f"Archive expands beyond the {max_total_bytes} byte limit"
            )

    return files


def stream_zip_entries(
    zip_bytes: bytes,
    *,
    batch_size: int = 1,
    max_files: int = DEFAULT_MAX_FILES,
    max_file_bytes: int = DEFAULT_MAX_FILE_BYTES,
    max_total_bytes: int = DEFAULT_MAX_TOTAL_BYTES,
) -> Iterator[list[tuple[str, bytes]]]:
    """Yield validated archive entries as batches of path and content."""
    if batch_size <= 0:
        raise ValueError("batch_size must be greater than zero")

    try:
        archive = zipfile.ZipFile(io.BytesIO(zip_bytes), mode="r")
    except zipfile.BadZipFile as exc:
        raise UnsafeArchiveError("Metadata response is not a valid ZIP archive") from exc

    with archive:
        files = _validated_files(
            archive,
            max_files=max_files,
            max_file_bytes=max_file_bytes,
            max_total_bytes=max_total_bytes,
        )
        batch: list[tuple[str, bytes]] = []
        actual_total_bytes = 0
        for info, relative_path in files:
            try:
                chunks: list[bytes] = []
                entry_bytes = 0
                with archive.open(info) as source:
                    while chunk := source.read(1024 * 1024):
                        entry_bytes += len(chunk)
                        actual_total_bytes += len(chunk)
                        if entry_bytes > max_file_bytes:
                            raise UnsafeArchiveError(
                                f"Archive entry is too large: {info.filename}"
                            )
                        if actual_total_bytes > max_total_bytes:
                            raise UnsafeArchiveError(
                                f"Archive expands beyond the {max_total_bytes} byte limit"
                            )
                        chunks.append(chunk)
                content = b"".join(chunks)
            except (zipfile.BadZipFile, RuntimeError) as exc:
                raise UnsafeArchiveError(
                    f"Could not read archive entry: {info.filename}"
                ) from exc
            batch.append((relative_path.as_posix(), content))
            if len(batch) == batch_size:
                yield batch
                batch = []
        if batch:
            yield batch


def extract_zip_to_directory(
    zip_bytes: bytes,
    destination: Path,
    *,
    max_files: int = DEFAULT_MAX_FILES,
    max_file_bytes: int = DEFAULT_MAX_FILE_BYTES,
    max_total_bytes: int = DEFAULT_MAX_TOTAL_BYTES,
) -> ExtractedArchive:
    """Safely write a metadata archive into a new destination directory."""
    destination = destination.expanduser().resolve()
    if destination.exists() and any(destination.iterdir()):
        raise FileExistsError(f"Extraction destination is not empty: {destination}")
    destination.mkdir(parents=True, exist_ok=True)

    paths: list[str] = []
    total_bytes = 0
    try:
        for batch in stream_zip_entries(
            zip_bytes,
            batch_size=1,
            max_files=max_files,
            max_file_bytes=max_file_bytes,
            max_total_bytes=max_total_bytes,
        ):
            relative_name, content = batch[0]
            relative_path = PurePosixPath(relative_name)
            output_path = destination.joinpath(*relative_path.parts)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with output_path.open("xb") as output_file:
                output_file.write(content)
            paths.append(relative_name)
            total_bytes += len(content)
    except Exception:
        shutil.rmtree(destination, ignore_errors=True)
        raise

    logger.info("Extracted %s metadata files into %s", len(paths), destination)
    return ExtractedArchive(
        destination=destination,
        file_count=len(paths),
        total_bytes=total_bytes,
        paths=tuple(paths),
    )
