import json
import tempfile
import unittest
from pathlib import Path

from steadfast.sitecheck import site_check_report


class SiteCheckTests(unittest.TestCase):
    def test_reports_complete_small_static_site(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            site = repo / "site"
            site.mkdir()
            (site / "index.html").write_text(
                '<!doctype html><html><head><title>Home</title>'
                '<meta name="description" content="A useful site">'
                '<link rel="canonical" href="https://example.test/">'
                '</head><body><h1>Home</h1><a href="about.html">About</a></body></html>',
                encoding="utf-8",
            )
            (site / "about.html").write_text(
                '<html><head><title>About</title><meta name="description" content="About">'
                '<link rel="canonical" href="https://example.test/about"></head><body><h1>About</h1></body></html>',
                encoding="utf-8",
            )
            (site / "sitemap.xml").write_text(
                '<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
                '<url><loc>https://example.test/</loc></url></urlset>',
                encoding="utf-8",
            )
            (site / "robots.txt").write_text("User-agent: *\nAllow: /\nSitemap: https://example.test/sitemap.xml\n", encoding="utf-8")
            result = site_check_report(repo, "site")
            self.assertEqual(result["status"], "passed")
            self.assertEqual(result["pages_scanned"], 2)
            self.assertEqual(result["errors"], 0)

    def test_reports_missing_metadata_and_broken_local_links(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            site = repo / "site"
            site.mkdir()
            (site / "index.html").write_text('<html><body><a href="missing.html">Missing</a></body></html>', encoding="utf-8")
            result = site_check_report(repo, "site")
            codes = {item["code"] for item in result["findings"]}
            self.assertIn("SITE_TITLE_MISSING", codes)
            self.assertIn("SITE_BROKEN_LOCAL_LINK", codes)
            self.assertGreater(result["errors"], 0)
            self.assertGreater(result["warnings"], 0)

    def test_refuses_site_directory_outside_repository(self):
        with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryDirectory() as outside:
            result = site_check_report(Path(directory), outside)
            self.assertEqual(result["status"], "error")
            self.assertEqual(result["findings"][0]["code"], "SITE_OUTSIDE_REPOSITORY")

    def test_missing_site_directory_is_an_error(self):
        with tempfile.TemporaryDirectory() as directory:
            result = site_check_report(Path(directory), "missing")
            self.assertEqual(result["findings"][0]["code"], "SITE_DIRECTORY_MISSING")


if __name__ == "__main__":
    unittest.main()
