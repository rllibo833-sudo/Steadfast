from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Mapping

NOTION_VERSION = "2022-06-28"
MAX_DOCUMENT_CHARS = 24_000
MAX_TOTAL_CHARS = 180_000
MAX_NOTION_BLOCKS = 400
LOCAL_ALLOWLIST = {
    "Cargo.toml",
    "device/profile.toml",
    "README.md",
}


def _http(url: str, *, token: str = "", headers: Mapping[str, str] | None = None) -> tuple[int, bytes, Mapping[str, str]]:
    request_headers = {"Accept": "application/json", "User-Agent": "steadfast-ncm-source-reader"}
    if token:
        request_headers["Authorization"] = f"Bearer {token}"
    request_headers.update(dict(headers or {}))
    request = urllib.request.Request(url, headers=request_headers, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=18) as response:
            return response.status, response.read(2_000_001), response.headers
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(4096), exc.headers
    except (urllib.error.URLError, TimeoutError, OSError):
        return 0, b"", {}


def _json(url: str, *, token: str = "", headers: Mapping[str, str] | None = None) -> tuple[int, dict[str, Any]]:
    status, body, _ = _http(url, token=token, headers=headers)
    if status != 200:
        return status, {}
    try:
        value = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return status, {}
    return status, value if isinstance(value, dict) else {"results": value}


def _page_id(uri: str) -> str | None:
    raw = urllib.parse.urlparse(uri).path.rstrip("/").split("/")[-1]
    value = re.sub(r"[^0-9a-fA-F]", "", raw)
    return value if len(value) == 32 else None


def _rich_text(items: Any) -> str:
    if not isinstance(items, list):
        return ""
    parts = []
    for item in items:
        if isinstance(item, dict):
            plain = item.get("plain_text")
            if isinstance(plain, str):
                parts.append(plain)
    return "".join(parts)


def _block_text(block: dict[str, Any]) -> str:
    kind = block.get("type")
    data = block.get(kind, {}) if isinstance(kind, str) else {}
    if not isinstance(data, dict):
        return ""
    if kind == "table_row":
        cells = data.get("cells", [])
        return " | ".join(_rich_text(cell) for cell in cells) if isinstance(cells, list) else ""
    if kind in {"child_page", "child_database"}:
        title = data.get("title")
        return title if isinstance(title, str) else ""
    return _rich_text(data.get("rich_text")) or _rich_text(data.get("title"))


def _notion_document(page_id: str, *, token: str) -> tuple[str, str]:
    headers = {"Notion-Version": NOTION_VERSION}
    status, page = _json(f"https://api.notion.com/v1/pages/{page_id}", token=token, headers=headers)
    if status != 200 or not isinstance(page.get("id"), str):
        return ("", "not_found_or_unauthorized" if status in (401, 403, 404) else "unreachable")
    properties = page.get("properties", {})
    title = ""
    if isinstance(properties, dict):
        for prop in properties.values():
            if isinstance(prop, dict) and prop.get("type") == "title":
                title = _rich_text(prop.get("title"))
                if title:
                    break
    lines = [f"# {title}"] if title else []
    count = 0
    incomplete = False

    def walk(parent_id: str, depth: int) -> None:
        nonlocal count, incomplete
        cursor = ""
        while count < MAX_NOTION_BLOCKS:
            query = {"page_size": "100"}
            if cursor:
                query["start_cursor"] = cursor
            url = f"https://api.notion.com/v1/blocks/{parent_id}/children?{urllib.parse.urlencode(query)}"
            block_status, payload = _json(url, token=token, headers=headers)
            if block_status != 200:
                incomplete = True
                return
            blocks = payload.get("results", [])
            if not isinstance(blocks, list):
                incomplete = True
                return
            for block in blocks:
                if not isinstance(block, dict):
                    continue
                count += 1
                kind = block.get("type")
                text = _block_text(block)
                if text.strip():
                    lines.append(text.strip())
                if kind in {"file", "pdf", "image", "video", "audio"}:
                    incomplete = True
                if block.get("has_children") is True:
                    child_id = block.get("id")
                    if depth >= 3 or not isinstance(child_id, str):
                        incomplete = True
                    else:
                        walk(child_id, depth + 1)
                if count >= MAX_NOTION_BLOCKS:
                    incomplete = True
                    break
            if incomplete or not payload.get("has_more"):
                return
            next_cursor = payload.get("next_cursor")
            if not isinstance(next_cursor, str) or not next_cursor:
                incomplete = True
                return
            cursor = next_cursor
        incomplete = True

    walk(page_id, 0)
    text = "\n".join(lines).strip()
    if len(text) > MAX_DOCUMENT_CHARS:
        incomplete = True
    return text[:MAX_DOCUMENT_CHARS], "partial" if incomplete else "read" if text else "empty"


def _github_readme(uri: str, *, token: str) -> tuple[str, str, str]:
    parsed = urllib.parse.urlparse(uri)
    parts = [part for part in parsed.path.split("/") if part]
    if parsed.netloc.lower() != "github.com" or len(parts) < 2:
        return "", "invalid_reference", ""
    owner, repo = parts[0], parts[1]
    api = f"https://api.github.com/repos/{urllib.parse.quote(owner)}/{urllib.parse.quote(repo)}/readme"
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    status, payload = _json(api, token=token, headers=headers)
    if status != 200:
        return "", "unavailable" if status in (401, 403, 404) else "unreachable", ""
    encoded = payload.get("content")
    if not isinstance(encoded, str):
        return "", "invalid_response", ""
    try:
        text = base64.b64decode(encoded).decode("utf-8", errors="replace")
    except (ValueError, base64.binascii.Error):
        return "", "invalid_response", ""
    truncated = len(text) > MAX_DOCUMENT_CHARS
    return text[:MAX_DOCUMENT_CHARS], "partial" if truncated else "read" if text else "empty", f"https://github.com/{owner}/{repo}/blob/{payload.get('sha', '')}"


def _local_documents(project: dict[str, Any], root: Path) -> list[dict[str, Any]]:
    result = []
    for relative in sorted(LOCAL_ALLOWLIST):
        path = root / relative
        try:
            if not path.is_file() or path.is_symlink():
                continue
            raw = path.read_bytes()
            if len(raw) > 128_000 or b"\x00" in raw:
                continue
            text = raw.decode("utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        result.append({
            "document_id": f"termux:{relative}",
            "project_id": project.get("id"),
            "source_id": "termux",
            "title": relative,
            "uri": relative,
            "content": text[:MAX_DOCUMENT_CHARS],
            "status": "read",
        })
    catalog = root / "modules" / "catalog"
    if catalog.is_dir() and not catalog.is_symlink():
        for path in sorted(catalog.glob("*.json"))[:40]:
            try:
                if path.is_symlink() or path.stat().st_size > 64_000:
                    continue
                text = path.read_text(encoding="utf-8")
                json.loads(text)
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                continue
            result.append({
                "document_id": f"termux:{path.relative_to(root).as_posix()}",
                "project_id": project.get("id"),
                "source_id": "termux",
                "title": path.name,
                "uri": path.relative_to(root).as_posix(),
                "content": text[:MAX_DOCUMENT_CHARS],
                "status": "read",
            })
    return result


def collect_source_documents(
    manifest: dict[str, Any],
    *,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Read bounded Notion pages, GitHub READMEs, and allowlisted local JBF metadata; never writes."""
    settings = os.environ if env is None else env
    notion_token = settings.get("NOTION_API_TOKEN", "").strip()
    github_token = settings.get("GITHUB_TOKEN", "").strip()
    jbf_root = Path(settings.get("JBF_ROOT") or (Path.home() / "JBF")).expanduser()
    documents: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    total_chars = 0

    for project in manifest.get("projects", []):
        if not isinstance(project, dict):
            continue
        refs = project.get("sources", [])
        if not isinstance(refs, list):
            continue
        for ref in refs:
            if not isinstance(ref, dict):
                continue
            source_id = ref.get("source_id")
            uri = ref.get("uri")
            if not isinstance(uri, str):
                continue
            if source_id == "notion":
                page_id = _page_id(uri)
                if not page_id or not notion_token:
                    failures.append({"project_id": project.get("id"), "source_id": "notion", "status": "not_configured" if not notion_token else "invalid_reference"})
                    continue
                key = ("notion", page_id)
                if key in seen:
                    continue
                seen.add(key)
                text, status = _notion_document(page_id, token=notion_token)
                title = ref.get("title") if isinstance(ref.get("title"), str) else page_id
                doc = {"document_id": f"notion:{page_id}", "project_id": project.get("id"), "source_id": "notion", "title": title, "uri": uri, "content": text, "status": status}
            elif source_id == "github":
                parsed = urllib.parse.urlparse(uri)
                parts = [part for part in parsed.path.split("/") if part]
                key = ("github", "/".join(parts[:2])) if len(parts) >= 2 else ("github", uri)
                if key in seen:
                    continue
                seen.add(key)
                text, status, resolved_uri = _github_readme(uri, token=github_token)
                doc = {"document_id": f"github:{key[1]}", "project_id": project.get("id"), "source_id": "github", "title": f"{project.get('name', key[1])} README", "uri": resolved_uri or uri, "content": text, "status": status}
            elif source_id in {"supabase", "cloudflare"}:
                # Metadata probes are not content access. Keep this explicit rather than implying ingestion.
                failures.append({"project_id": project.get("id"), "source_id": source_id, "status": "content_reader_not_implemented"})
                continue
            else:
                continue
            if doc["status"] not in {"read", "partial"}:
                failures.append({"project_id": project.get("id"), "source_id": source_id, "status": doc["status"]})
                continue
            remaining = MAX_TOTAL_CHARS - total_chars
            if remaining <= 0:
                failures.append({"project_id": project.get("id"), "source_id": source_id, "status": "total_content_limit_reached"})
                continue
            original_length = len(doc["content"])
            doc["content"] = doc["content"][:min(MAX_DOCUMENT_CHARS, remaining)]
            doc["truncated"] = doc.get("status") == "partial" or len(doc["content"]) < original_length
            if doc["truncated"]:
                doc["status"] = "partial"
            total_chars += len(doc["content"])
            doc["content_sha256"] = hashlib.sha256(doc["content"].encode("utf-8")).hexdigest()
            documents.append(doc)

        if project.get("id") == "jbf-sandboxos" and jbf_root.is_dir():
            for doc in _local_documents(project, jbf_root):
                remaining = MAX_TOTAL_CHARS - total_chars
                if remaining <= 0:
                    break
                original_length = len(doc["content"])
                doc["content"] = doc["content"][:min(MAX_DOCUMENT_CHARS, remaining)]
                doc["truncated"] = len(doc["content"]) < original_length
                if doc["truncated"]:
                    doc["status"] = "partial"
                total_chars += len(doc["content"])
                doc["content_sha256"] = hashlib.sha256(doc["content"].encode("utf-8")).hexdigest()
                documents.append(doc)

    return {
        "schema_version": "1.0.0",
        "artifact_type": "ncm-source-documents",
        "documents": documents,
        "failures": failures,
        "summary": {
            "documents_read": len(documents),
            "characters_read": total_chars,
            "sources_with_failures": len(failures),
            "partial_documents": sum(item.get("status") == "partial" for item in documents),
        },
        "safety": {
            "http_method": "GET",
            "remote_writes": False,
            "local_files_modified": False,
            "local_file_allowlist_only": True,
            "credentials_in_output": False,
            "content_sent_to_model": False,
        },
    }
