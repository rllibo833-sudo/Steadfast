import base64
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from steadfast.ncm_sources import _github_readme, _notion_document, collect_source_documents


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

    def test_existing_jbf_github_token_is_used_when_actions_token_is_absent(self):
        manifest = {"projects": [{"id": "p", "name": "Project", "sources": [
            {"source_id": "github", "uri": "https://github.com/example/project"},
        ]}]}
        with patch("steadfast.ncm_sources._github_readme", return_value=("# README", "read", "https://github.com/example/project")) as reader:
            result = collect_source_documents(manifest, env={"JBF_GITHUB_TOKEN": "existing-token"})
        self.assertEqual(result["summary"]["documents_read"], 1)
        self.assertEqual(reader.call_args.kwargs["token"], "existing-token")

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

    def test_local_document_truncation_is_reported_as_partial(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text("A" * 40, encoding="utf-8")
            manifest = {"projects": [{"id": "jbf-sandboxos", "name": "JBF", "sources": []}]}
            with patch("steadfast.ncm_sources.MAX_DOCUMENT_CHARS", 12):
                result = collect_source_documents(manifest, env={"JBF_ROOT": directory})
        document = result["documents"][0]
        self.assertEqual(document["content"], "A" * 12)
        self.assertEqual(document["status"], "partial")
        self.assertEqual(result["summary"]["partial_documents"], 1)

    def test_content_artifact_marks_unsupported_services_instead_of_claiming_read(self):
        manifest = {"projects": [{"id": "p", "sources": [
            {"source_id": "supabase", "uri": "supabase://project/vcvejjpzklpvknxmymgy"},
            {"source_id": "cloudflare", "uri": "cloudflare://worker/example"},
        ]}]}
        result = collect_source_documents(manifest, env={})
        statuses = {item["source_id"]: item["status"] for item in result["failures"]}
        self.assertEqual(statuses["supabase"], "not_configured")
        self.assertEqual(statuses["cloudflare"], "not_configured")
        self.assertEqual(result["documents"], [])

    def test_notion_nested_blocks_are_read_and_depth_is_bounded(self):
        page = {"id": "page", "properties": {}}
        parent = {"results": [{
            "id": "child", "type": "toggle", "has_children": True,
            "toggle": {"rich_text": [{"plain_text": "Parent section"}]},
        }], "has_more": False}
        child = {"results": [{
            "id": "grandchild", "type": "paragraph",
            "paragraph": {"rich_text": [{"plain_text": "Nested evidence"}]},
        }], "has_more": False}
        with patch("steadfast.ncm_sources._json", side_effect=[(200, page), (200, parent), (200, child)]):
            content, status = _notion_document("a" * 32, token="token")
        self.assertEqual(status, "read")
        self.assertIn("Parent section", content)
        self.assertIn("Nested evidence", content)

    def test_notion_content_limit_is_reported_as_partial(self):
        page = {"id": "page", "properties": {}}
        blocks = {"results": [{
            "type": "paragraph",
            "paragraph": {"rich_text": [{"plain_text": "A much longer paragraph than the configured cap"}]},
        }], "has_more": False}
        with patch("steadfast.ncm_sources.MAX_DOCUMENT_CHARS", 12):
            with patch("steadfast.ncm_sources._json", side_effect=[(200, page), (200, blocks)]):
                content, status = _notion_document("a" * 32, token="token")
        self.assertEqual(len(content), 12)
        self.assertEqual(status, "partial")


    def test_supabase_reader_uses_explicit_table_and_column_allowlist(self):
        project_ref = "vcvejjpzklpvknxmymgy"
        manifest = {"projects": [{"id": "p", "name": "P", "sources": [
            {"source_id": "supabase", "uri": f"supabase://project/{project_ref}"},
        ]}]}
        allowlist = json.dumps([{"project_ref": project_ref, "table": "public.notes", "columns": ["id", "title"]}])
        with patch("steadfast.ncm_sources._http", return_value=(200, b'[{"id":1,"title":"hello"}]', {"Content-Type": "application/json"})) as request:
            result = collect_source_documents(manifest, env={"SUPABASE_PUBLISHABLE_KEY": "sb_publishable_test", "SUPABASE_READ_ALLOWLIST": allowlist})
        self.assertEqual(result["summary"]["documents_read"], 1)
        self.assertIn('"title": "hello"', result["documents"][0]["content"])
        self.assertIn("select=id%2Ctitle", request.call_args.args[0])
        self.assertEqual(request.call_args.kwargs["headers"]["apikey"], "sb_publishable_test")
        self.assertNotIn("service_role", request.call_args.kwargs["headers"].get("Authorization", ""))

    def test_supabase_reader_refuses_unlisted_tables(self):
        project_ref = "vcvejjpzklpvknxmymgy"
        manifest = {"projects": [{"id": "p", "sources": [
            {"source_id": "supabase", "uri": f"supabase://project/{project_ref}"},
        ]}]}
        result = collect_source_documents(manifest, env={"SUPABASE_PUBLISHABLE_KEY": "sb_publishable_test"})
        self.assertEqual(result["documents"], [])
        self.assertEqual(result["failures"][0]["status"], "not_configured")

    def test_cloudflare_worker_reader_is_get_only_and_captures_source(self):
        manifest = {"projects": [{"id": "edge-app", "name": "Edge App", "sources": [
            {"source_id": "cloudflare", "uri": "cloudflare://worker/edge-api"},
        ]}]}
        with patch("steadfast.ncm_sources._http", return_value=(200, b"export default { fetch() { return new Response('ok') } }", {"Content-Type": "text/javascript"})) as request:
            result = collect_source_documents(manifest, env={"CLOUDFLARE_ACCOUNT_ID": "a" * 32, "CLOUDFLARE_API_TOKEN": "token"})
        self.assertEqual(result["summary"]["documents_read"], 1)
        self.assertIn("new Response", result["documents"][0]["content"])
        self.assertTrue(request.call_args.args[0].endswith("/workers/scripts/edge-api"))
        self.assertEqual(request.call_args.kwargs["token"], "token")

    def test_cloudflare_reader_requires_account_and_token(self):
        manifest = {"projects": [{"id": "edge-app", "sources": [
            {"source_id": "cloudflare", "uri": "cloudflare://worker/edge-api"},
        ]}]}
        result = collect_source_documents(manifest, env={})
        self.assertEqual(result["documents"], [])
        self.assertEqual(result["failures"][0]["status"], "not_configured")


    def test_supabase_reader_rejects_secret_key(self):
        project_ref = "vcvejjpzklpvknxmymgy"
        manifest = {"projects": [{"id": "p", "sources": [
            {"source_id": "supabase", "uri": f"supabase://project/{project_ref}"},
        ]}]}
        allowlist = json.dumps([{"project_ref": project_ref, "table": "public.notes", "columns": ["id"]}])
        result = collect_source_documents(manifest, env={"SUPABASE_PUBLISHABLE_KEY": "sb_secret_never-use", "SUPABASE_READ_ALLOWLIST": allowlist})
        self.assertEqual(result["documents"], [])
        self.assertEqual(result["failures"][0]["status"], "not_configured")


if __name__ == "__main__":
    unittest.main()
