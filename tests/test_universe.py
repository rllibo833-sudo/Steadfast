from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from steadfast.universe import universe_report


class UniverseManifestTests(unittest.TestCase):
    def test_valid_manifest_passes_without_network_or_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "ecosystem").mkdir()
            manifest = {
                "manifest_version": "1.0",
                "universe_id": "test",
                "sources": [{"id": "github", "type": "git", "state": "connected"}],
                "projects": [{
                    "id": "alpha", "name": "Alpha", "purpose": "test",
                    "status": "unverified",
                    "sources": [{"source_id": "github", "uri": "https://github.com/example/alpha", "role": "repository"}],
                }],
                "relationships": [{"from": "alpha", "to": "harness", "type": "indexed_by", "status": "proposed"}],
            }
            path = root / "ecosystem" / "universe.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            result = universe_report(root)
            self.assertTrue(result["passed"])
            self.assertEqual(result["summary"]["projects"], 1)
            self.assertFalse(result["safety"]["network_requests_made"])
            self.assertFalse(result["safety"]["project_files_modified"])

    def test_detects_duplicate_ids_unknown_sources_and_relationship_nodes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "ecosystem").mkdir()
            manifest = {
                "manifest_version": "1.0",
                "universe_id": "test",
                "sources": [{"id": "git"}, {"id": "git"}],
                "projects": [
                    {"id": "alpha", "sources": [{"source_id": "missing", "uri": "https://example.com"}]},
                    {"id": "alpha", "sources": []},
                ],
                "relationships": [{"from": "alpha", "to": "ghost"}],
            }
            (root / "ecosystem" / "universe.json").write_text(json.dumps(manifest), encoding="utf-8")
            result = universe_report(root)
            codes = {item["code"] for item in result["findings"]}
            self.assertFalse(result["passed"])
            self.assertIn("UNIVERSE_DUPLICATE_SOURCE", codes)
            self.assertIn("UNIVERSE_DUPLICATE_PROJECT", codes)
            self.assertIn("UNIVERSE_UNKNOWN_SOURCE", codes)
            self.assertIn("UNIVERSE_UNKNOWN_ENDPOINT", codes)

    def test_invalid_json_is_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "ecosystem").mkdir()
            (root / "ecosystem" / "universe.json").write_text("{broken", encoding="utf-8")
            result = universe_report(root)
            self.assertFalse(result["passed"])
            self.assertEqual(result["findings"][0]["code"], "UNIVERSE_INVALID_JSON")


if __name__ == "__main__":
    unittest.main()
