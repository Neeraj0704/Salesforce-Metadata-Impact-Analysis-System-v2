"""Tests for normalized Salesforce metadata parsing."""

import json
import tempfile
import unittest
from pathlib import Path

from metadata_fixtures import build_metadata_zip
from src.metadata_api.zip_extractor import extract_zip_to_directory
from src.metadata_parser.service import parse_metadata_workspace


class MetadataParserTests(unittest.TestCase):
    def test_parses_supported_metadata_and_relationships(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory)
            metadata_root = workspace / "metadata"
            extract_zip_to_directory(build_metadata_zip(), metadata_root)
            output_path = workspace / "analysis/parsed_metadata.json"

            result = parse_metadata_workspace(
                metadata_root,
                output_path=output_path,
            )

            component_keys = {component.key for component in result.components}
            self.assertTrue(
                {
                    "CustomObject:Invoice__c",
                    "CustomField:Invoice__c.Account__c",
                    "CustomField:Invoice__c.Status__c",
                    "ApexClass:InvoiceService",
                    "ApexTrigger:InvoiceTrigger",
                    "Flow:Update_Invoice",
                    "PermissionSet:Invoice_User",
                }.issubset(component_keys)
            )

            references = {
                (reference.source_key, reference.relationship, reference.target_key)
                for reference in result.references
            }
            self.assertIn(
                (
                    "CustomField:Invoice__c.Account__c",
                    "REFERENCES_OBJECT",
                    "CustomObject:Account",
                ),
                references,
            )
            self.assertIn(
                (
                    "Flow:Update_Invoice",
                    "USES_FIELD",
                    "CustomField:Invoice__c.Status__c",
                ),
                references,
            )
            self.assertIn(
                (
                    "PermissionSet:Invoice_User",
                    "GRANTS_APEX_ACCESS",
                    "ApexClass:InvoiceService",
                ),
                references,
            )
            self.assertIn(
                (
                    "ApexTrigger:InvoiceTrigger",
                    "TRIGGERS_ON",
                    "CustomObject:Invoice__c",
                ),
                references,
            )
            self.assertEqual(result.warnings, [])
            saved = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(len(saved["components"]), result.component_count)

    def test_malformed_file_becomes_warning(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            metadata_root = Path(temporary_directory)
            bad_file = metadata_root / "objects/Bad.object"
            bad_file.parent.mkdir()
            bad_file.write_text("<CustomObject>", encoding="utf-8")

            result = parse_metadata_workspace(metadata_root)

            self.assertEqual(result.component_count, 0)
            self.assertEqual(len(result.warnings), 1)


if __name__ == "__main__":
    unittest.main()
