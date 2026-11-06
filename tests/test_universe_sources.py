import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from steadfast.universe_sources import source_report


class UniverseSourceTests(unittest.TestCase):
    def test_unconfigured_services_are_not_reported_as_connected(self):
        result = source_report({"projects": []}, repo=".", env={})
        self.assertEqual(result["summary"]["not_configured"], 3)
        self.assertFalse(result["safety"]["remote_writes"])
        self.assertFalse(result["safety"]["credentials_in_output"])

    def test_termux_probe_only_checks_expected_metadata_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "device").mkdir()
            (root / "device" / "profile.toml").write_text("[device]", encoding="utf-8")
            result = source_report({"projects": []}, repo=".", env={"JBF_ROOT": directory})
            termux = next(item for item in result["sources"] if item["source"] == "termux")
            self.assertEqual(termux["status"], "partial")
            self.assertTrue(any(item["path"] == "device/profile.toml" and item["present"] for item in termux["items"]))

    def test_supabase_inactive_is_distinct_from_unreachable(self):
        manifest = {"projects": [{"id": "x", "sources": [{"source_id": "supabase", "uri": "supabase://project/abcdefgh12345678"}]}]}
        with patch("steadfast.universe_sources._request_json", return_value={"id": "abcdefgh12345678", "status": "INACTIVE"}):
            result = source_report(manifest, repo=".", env={"SUPABASE_ACCESS_TOKEN": "token"})
        item = next(item for source in result["sources"] if source["source"] == "supabase" for item in source["items"])
        self.assertEqual(item["status"], "inactive")


if __name__ == "__main__":
    unittest.main()
