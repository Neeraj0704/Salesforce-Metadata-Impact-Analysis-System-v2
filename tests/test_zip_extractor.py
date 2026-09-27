"""Tests for safe Salesforce metadata ZIP extraction."""

import io
import tempfile
import unittest
import zipfile
from pathlib import Path

from metadata_fixtures import build_metadata_zip
from src.metadata_api.zip_extractor import (
    UnsafeArchiveError,
    extract_zip_to_directory,
    stream_zip_entries,
)


class ZipExtractorTests(unittest.TestCase):
    def test_extracts_normal_relative_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            destination = Path(temporary_directory) / "metadata"
            result = extract_zip_to_directory(build_metadata_zip(), destination)

            self.assertEqual(result.file_count, 6)
            self.assertTrue(
                (destination / "unpackaged/objects/Invoice__c.object").is_file()
            )

    def test_streams_files_in_batches(self) -> None:
        batches = list(stream_zip_entries(build_metadata_zip(), batch_size=2))
        self.assertEqual([len(batch) for batch in batches], [2, 2, 2])

    def test_rejects_parent_path(self) -> None:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("../escape.txt", "unsafe")

        with tempfile.TemporaryDirectory() as temporary_directory:
            with self.assertRaisesRegex(UnsafeArchiveError, "Unsafe archive path"):
                extract_zip_to_directory(
                    buffer.getvalue(),
                    Path(temporary_directory) / "metadata",
                )

    def test_rejects_invalid_zip(self) -> None:
        with self.assertRaisesRegex(UnsafeArchiveError, "not a valid ZIP"):
            list(stream_zip_entries(b"not-a-zip"))

    def test_rejects_file_over_size_limit(self) -> None:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("large.txt", "12345")

        with self.assertRaisesRegex(UnsafeArchiveError, "too large"):
            list(stream_zip_entries(buffer.getvalue(), max_file_bytes=4))


if __name__ == "__main__":
    unittest.main()
