"""Stream-based ZIP extractor for Salesforce metadata. No disk extraction."""

import io
import logging
import zipfile
from pathlib import Path
from typing import Iterator

logger = logging.getLogger(__name__)


def _is_safe_path(name: str) -> bool:
    """Check for zip slip and invalid paths."""
    path = Path(name)
    parts = path.parts
    if ".." in parts:
        return False
    if path.is_absolute() or str(path.resolve()).startswith("/"):
        return False
    return True


def stream_zip_entries(
    zip_bytes: bytes,
    *,
    batch_size: int = 1,
) -> Iterator[list[tuple[str, bytes]]]:
    """Stream ZIP entries as batches of (file_path, content).

    Args:
        zip_bytes: Raw ZIP file bytes.
        batch_size: Number of entries per batch. Use 1 for true one-at-a-time.

    Yields:
        Batches of (file_path, content) tuples.
    """
    with zipfile.ZipFile(io.BytesIO(zip_bytes), mode="r") as zf:
        batch: list[tuple[str, bytes]] = []
        for name in zf.namelist():
            if name.endswith("/"):
                continue
            if not _is_safe_path(name):
                logger.warning("Skipping unsafe path: %s", name)
                continue
            try:
                with zf.open(name) as f:
                    content = f.read()
            except (zipfile.BadZipFile, KeyError) as e:
                logger.warning("Failed to read %s: %s", name, e)
                continue
            batch.append((name, content))
            if len(batch) >= batch_size:
                yield batch
                batch = []
        if batch:
            yield batch