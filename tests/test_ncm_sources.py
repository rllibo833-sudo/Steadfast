import base64
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from steadfast.ncm_sources import collect_source_documents, _notion_document, _github_readme


class NcmSourceIngestionTests(unittest.TestCase):
    def test_notion_page_blocks_are_flattened_with_pagination(self):
        first = {"id": "page", "properties": {"title": {"type": "title", "title": [{"plain_text": "Test page"}]}}}
        page1 = {"results": [{"type": "paragraph", "paragraph": {"rich_text": [{"plain_text": "First paragraph"}]}}], "has_more": True, "next_cursor": "next"}
        page2 = {"results": [{"type": "heading_2", "heading_2": {"rich_text": [{"plain_text": "Second section"}]}}], "has_more": False}
        with patch("steadfast.ncm_sources._json", side_effect=[(200, first), (200, page1), (200, page2)]):
            content, status = _notion_document("a" * 32, token="token")
        self.assertEqual(status, "read")
        self.assertIn("# Test page", content)
        self.assertIn("First paragraph", content)
        self.assertIn("Second section", content)

    def test_github_readme_decodes_content(self):
        encoded = base64.b64encode(b"# Repo\nProject purpose").decode("ascii")
        with patch("steadfast.ncm_sources._json", return_value=(200, {"content": encoded, "sha": "abc123"})):
            content, status, uri = _github_readme("https://github.com/example/project", token="")
        self.assertEqual(status, "read")
        self.assertIn("Project purpose", content)
        self.assertIn("/blob/abc123", uri)

    def test_local_jbf_ingestion_uses_allowlist_and_skips_symlinks(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "device").mkdir()
            (root / "modules" / "catalog").mkdir(parents=True)
            (root / "Cargo.toml").write_text("[package]\nname='jbf'\n", encoding="utf-8")
            (root / "device" / "profile.toml").write_text("[device]\nmodel='V2333'\n", encoding="utf-8")
            (root / "modules" / "catalog" / "module.json").write_text(json.dumps({"id": "sensor"}), encoding="utf-8")
            (root / ".env").write_text("SECRET=must-not-read", encoding="utf-8")
            manifest = {"projects": [{"id": "jbf-sandboxos", "name": "JBF", "sources": []}]}
            result = collect_source_documents(manifest, env={"JBF_ROOT": directory})
        content = "\n".join(item["content"] for item in result["documents"])
        self.assertEqual(result["summary"]["documents_read"], 3)
        self.assertNotIn("must-not-read", content)
        self.assertTrue(result["safety"]["local_file_allowlist_only"])

    def test_content_artifact_marks_unsupported_services_instead_of_claiming_read(self):
        manifest = {"projects": [{"id": "p", "sources": [
            {"source_id": "supabase", "uri": "supabase://project/abcdefgh"},
            {"source_id": "cloudflare", "uri": "cloudflare://worker/example"},
        ]}]}
        result = collect_source_documents(manifest, env={})
        statuses = {item["source_id"]: item["status"] for item in result["failures"]}
        self.assertEqual(statuses["supabase"], "content_reader_not_implemented")
        self.assertEqual(statuses["cloudflare"], "content_reader_not_implemented")
        self.assertEqual(result["documents"], [])


if __name__ == "__main__":
    unittest.main()
