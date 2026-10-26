from __future__ import annotations

import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from steadfast.evidence_bundle import (
    EvidenceBundleError,
    build_evidence_bundle,
    verify_evidence_bundle,
)
from steadfast.policy import init_policy


class EvidenceBundleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.repo = Path(self.temp.name)
        init_policy(self.repo)
        (self.repo / ".steadfast" / "goal.md").write_text(
            "# Product goal\n\n## Acceptance criteria\n- [ ] Evidence packages verify\n",
            encoding="utf-8",
        )
        (self.repo / "implementation.py").write_text("VALUE = 42\n", encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def test_build_and_verify_portable_bundle(self):
        result = build_evidence_bundle(self.repo, ".steadfast/artifacts/release.zip")
        self.assertEqual(result["status"], "built")
        verified = verify_evidence_bundle(self.repo, result["path"])
        self.assertTrue(verified["valid"])
        self.assertEqual(verified["commit"], result["commit"])
        with zipfile.ZipFile(self.repo / result["path"]) as archive:
            self.assertEqual(set(archive.namelist()), {"manifest.json", "evidence.json"})
            report = json.loads(archive.read("evidence.json"))
            self.assertEqual(report["schema_version"], 1)
            self.assertNotIn(str(self.repo), json.dumps(report))
            self.assertIn("inventory", report["components"])
            self.assertIn("change_impact", report["components"])
            self.assertIn("work_orders", report["components"])

    def test_existing_output_requires_explicit_overwrite(self):
        build_evidence_bundle(self.repo, ".steadfast/artifacts/release.zip")
        with self.assertRaisesRegex(EvidenceBundleError, "already exists"):
            build_evidence_bundle(self.repo, ".steadfast/artifacts/release.zip")
        result = build_evidence_bundle(self.repo, ".steadfast/artifacts/release.zip", overwrite=True)
        self.assertEqual(result["status"], "built")

    def test_modified_payload_is_rejected(self):
        result = build_evidence_bundle(self.repo, ".steadfast/artifacts/release.zip")
        path = self.repo / result["path"]
        with zipfile.ZipFile(path, "r") as source:
            manifest = source.read("manifest.json")
            evidence = source.read("evidence.json") + b" "
        with zipfile.ZipFile(path, "w") as target:
            target.writestr("manifest.json", manifest)
            target.writestr("evidence.json", evidence)
        with self.assertRaisesRegex(EvidenceBundleError, "checksum or size"):
            verify_evidence_bundle(self.repo, result["path"])

    def test_path_traversal_and_unexpected_archive_entries_are_rejected(self):
        with self.assertRaisesRegex(EvidenceBundleError, "repository-relative"):
            verify_evidence_bundle(self.repo, "../escape.zip")
        result = build_evidence_bundle(self.repo, ".steadfast/artifacts/release.zip")
        path = self.repo / result["path"]
        with zipfile.ZipFile(path, "a") as archive:
            archive.writestr("../outside.txt", "not allowed")
        with self.assertRaisesRegex(EvidenceBundleError, "unexpected"):
            verify_evidence_bundle(self.repo, result["path"])


if __name__ == "__main__":
    unittest.main()
