from __future__ import annotations

from html.parser import HTMLParser
import json
from pathlib import Path
from urllib.parse import unquote, urlsplit
import xml.etree.ElementTree as ET
from typing import Any


class _PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.description = ""
        self.canonical = ""
        self.robots = ""
        self.h1_count = 0
        self.links: list[str] = []
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key.lower(): value or "" for key, value in attrs}
        if tag.lower() == "title":
            self._in_title = True
        elif tag.lower() == "h1":
            self.h1_count += 1
        elif tag.lower() == "meta":
            name = values.get("name", "").strip().lower()
            if name == "description":
                self.description = values.get("content", "").strip()
            elif name == "robots":
                self.robots = values.get("content", "").strip().lower()
        elif tag.lower() == "link" and values.get("rel", "").lower() == "canonical":
            self.canonical = values.get("href", "").strip()
        if tag.lower() in {"a", "area", "link", "script", "img", "source", "iframe"}:
            target = values.get("href") or values.get("src")
            if target:
                self.links.append(target.strip())

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title += data


def site_check_report(repo: Path, site: str) -> dict[str, Any]:
    """Audit a repository-contained static site using local files only."""
    root_repo = repo.resolve()
    candidate = Path(site)
    if not candidate.is_absolute():
        candidate = root_repo / candidate
    try:
        root = candidate.resolve(strict=False)
        root.relative_to(root_repo)
    except (OSError, ValueError):
        return {
            "site": site,
            "status": "error",
            "pages_scanned": 0,
            "errors": 1,
            "warnings": 0,
            "findings": [{
                "severity": "error",
                "code": "SITE_OUTSIDE_REPOSITORY",
                "path": site,
                "message": "Site directory must stay inside the selected repository.",
            }],
        }
    if not root.is_dir():
        return {
            "site": site,
            "status": "error",
            "pages_scanned": 0,
            "errors": 1,
            "warnings": 0,
            "findings": [{
                "severity": "error",
                "code": "SITE_DIRECTORY_MISSING",
                "path": site,
                "message": "Static site directory does not exist.",
            }],
        }

    findings: list[dict[str, str]] = []

    def add(severity: str, code: str, path: str, message: str) -> None:
        findings.append({"severity": severity, "code": code, "path": path, "message": message})

    pages = sorted(path for path in root.rglob("*.html") if path.is_file() and not any(part.startswith(".") for part in path.relative_to(root).parts))
    if not pages:
        add("error", "SITE_NO_HTML", site, "No HTML pages were found in the site directory.")

    for page in pages:
        relative = page.relative_to(root).as_posix()
        try:
            source = page.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            add("error", "SITE_HTML_UNREADABLE", relative, f"Cannot read HTML as UTF-8: {type(exc).__name__}.")
            continue
        parser = _PageParser()
        try:
            parser.feed(source)
            parser.close()
        except Exception:
            add("error", "SITE_HTML_MALFORMED", relative, "HTML parser could not finish this page.")
            continue
        if not parser.title.strip():
            add("error", "SITE_TITLE_MISSING", relative, "Add a non-empty <title>.")
        if not parser.description:
            add("warning", "SITE_DESCRIPTION_MISSING", relative, "Add a meta description for search and link previews.")
        if not parser.canonical:
            add("warning", "SITE_CANONICAL_MISSING", relative, "Add a canonical URL when this page has a public canonical address.")
        if parser.h1_count == 0:
            add("warning", "SITE_H1_MISSING", relative, "Add a main heading so the page's subject is clear.")
        if "noindex" in parser.robots:
            add("warning", "SITE_NOINDEX", relative, "This page tells search engines not to index it.")
        for raw_target in parser.links:
            parsed = urlsplit(raw_target)
            if parsed.scheme or parsed.netloc or not parsed.path or raw_target.startswith("#"):
                continue
            path_part = unquote(parsed.path)
            target = (root / path_part.lstrip("/")) if path_part.startswith("/") else (page.parent / path_part)
            try:
                resolved = target.resolve(strict=False)
                resolved.relative_to(root)
            except (OSError, ValueError):
                add("error", "SITE_LINK_OUTSIDE_ROOT", relative, f"Local link escapes the site directory: {raw_target}")
                continue
            if resolved.is_dir():
                resolved = resolved / "index.html"
            if not resolved.is_file():
                add("error", "SITE_BROKEN_LOCAL_LINK", relative, f"Local link target does not exist: {raw_target}")

    sitemap = root / "sitemap.xml"
    if not sitemap.is_file():
        add("warning", "SITE_SITEMAP_MISSING", "sitemap.xml", "Add a sitemap.xml so crawlers can discover public pages.")
    else:
        try:
            sitemap_root = ET.parse(sitemap).getroot()
            if not sitemap_root.tag.endswith("urlset"):
                add("error", "SITE_SITEMAP_INVALID_ROOT", "sitemap.xml", "Sitemap root element must be urlset.")
            locs = [item.text.strip() for item in sitemap_root.iter() if item.tag.endswith("loc") and item.text and item.text.strip()]
            if not locs:
                add("warning", "SITE_SITEMAP_EMPTY", "sitemap.xml", "Sitemap contains no URL entries.")
        except (ET.ParseError, OSError, UnicodeError):
            add("error", "SITE_SITEMAP_INVALID", "sitemap.xml", "Sitemap is not readable, well-formed XML.")

    robots = root / "robots.txt"
    if not robots.is_file():
        add("warning", "SITE_ROBOTS_MISSING", "robots.txt", "Add robots.txt with a Sitemap declaration.")
    else:
        try:
            robots_text = robots.read_text(encoding="utf-8")
            if sitemap.is_file() and "sitemap:" not in robots_text.lower():
                add("warning", "SITE_ROBOTS_NO_SITEMAP", "robots.txt", "Declare the public sitemap URL in robots.txt.")
        except (OSError, UnicodeError):
            add("error", "SITE_ROBOTS_UNREADABLE", "robots.txt", "robots.txt cannot be read as UTF-8.")

    errors = sum(item["severity"] == "error" for item in findings)
    warnings = sum(item["severity"] == "warning" for item in findings)
    return {
        "site": root.relative_to(root_repo).as_posix(),
        "status": "failed" if errors else ("warnings" if warnings else "passed"),
        "pages_scanned": len(pages),
        "errors": errors,
        "warnings": warnings,
        "findings": findings,
    }
