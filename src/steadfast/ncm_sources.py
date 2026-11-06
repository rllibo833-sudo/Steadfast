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



def _supabase_allowlist(raw: str) -> list[dict[str, Any]]:
    try:
        entries = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return []
    if not isinstance(entries, list):
        return []
    valid = []
    for item in entries:
        if not isinstance(item, dict):
            continue
        project_ref, table, columns = item.get("project_ref"), item.get("table"), item.get("columns")
        if not isinstance(project_ref, str) or not re.fullmatch(r"[a-z0-9]{20}", project_ref):
            continue
        if not isinstance(table, str) or not re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_]*\.[a-zA-Z_][a-zA-Z0-9_]*", table):
            continue
        if not isinstance(columns, list) or not columns or len(columns) > 40:
            continue
        if not all(isinstance(column, str) and re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_]*", column) for column in columns):
            continue
        valid.append({"project_ref": project_ref, "table": table, "columns": columns})
    return valid


def _supabase_table(project_ref: str, entry: dict[str, Any], *, key: str) -> tuple[str, str, str]:
    schema, table = entry["table"].split(".", 1)
    columns = ",".join(entry["columns"])
    query = urllib.parse.urlencode({"select": columns, "limit": "100"})
    url = f"https://{project_ref}.supabase.co/rest/v1/{urllib.parse.quote(table)}?{query}"
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Accept": "application/json",
        "Range": "0-99",
        "Accept-Profile": schema,
    }
    status, body, _ = _http(url, headers=headers)
    if status != 200:
        return "", "unavailable" if status in (401, 403, 404, 502, 503, 522) or status == 0 else "read_failed", ""
    try:
        rows = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return "", "invalid_response", ""
    if not isinstance(rows, list):
        return "", "invalid_response", ""
    content = json.dumps(rows, ensure_ascii=False, sort_keys=True, indent=2)
    truncated = len(content) > MAX_DOCUMENT_CHARS
    return content[:MAX_DOCUMENT_CHARS], "partial" if truncated or len(rows) >= 100 else "read" if rows else "empty", url


def _cloudflare_worker(account_id: str, script_name: str, *, token: str) -> tuple[str, str, str]:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", script_name):
        return "", "invalid_reference", ""
    url = (
        "https://api.cloudflare.com/client/v4/accounts/"
        + urllib.parse.quote(account_id, safe="")
        + "/workers/scripts/"
        + urllib.parse.quote(script_name, safe="")
    )
    status, body, headers = _http(url, token=token, headers={"Accept": "*/*"})
    if status != 200:
        return "", "unavailable" if status in (401, 403, 404) or status == 0 else "read_failed", ""
    content_type = str(headers.get("Content-Type", "")).lower()
    if "multipart/" in content_type:
        try:
            from email import policy
            from email.parser import BytesParser
            message = BytesParser(policy=policy.default).parsebytes(
                b"Content-Type: " + str(headers.get("Content-Type", "")).encode("ascii", "replace")
                + b"\r\nMIME-Version: 1.0\r\n\r\n" + body
            )
            parts = []
            for part in message.walk():
                if part.is_multipart():
                    continue
                payload = part.get_payload(decode=True)
                if payload:
                    parts.append(payload.decode("utf-8"))
            body_text = "\n\n".join(parts)
        except (UnicodeDecodeError, ValueError):
            return "", "partial", url
    else:
        try:
            body_text = body.decode("utf-8")
        except UnicodeDecodeError:
            return "", "unsupported_binary_content", url
    if not body_text.strip():
        return "", "empty", url
    truncated = len(body_text) > MAX_DOCUMENT_CHARS
    return body_text[:MAX_DOCUMENT_CHARS], "partial" if truncated else "read", url


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
    """Read bounded Notion, GitHub, allowlisted Supabase tables, Cloudflare Workers, and local JBF metadata; never writes."""
    settings = os.environ if env is None else env
    notion_token = settings.get("NOTION_API_TOKEN", "").strip()
    # Prefer the Actions-provided token; reuse the repository secret for local/manual runs.
    github_token = (settings.get("GITHUB_TOKEN") or settings.get("JBF_GITHUB_TOKEN") or "").strip()
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
            elif source_id == "supabase":
                parsed = urllib.parse.urlparse(uri)
                project_ref = parsed.path.strip("/").split("/")[0] if parsed.scheme == "supabase" else ""
                if not re.fullmatch(r"[a-z0-9]{20}", project_ref):
                    failures.append({"project_id": project.get("id"), "source_id": source_id, "status": "invalid_reference"})
                    continue
                key = ("supabase", project_ref)
                if key in seen:
                    continue
                seen.add(key)
                api_key = settings.get("SUPABASE_PUBLISHABLE_KEY", "").strip()
                allowlist = [item for item in _supabase_allowlist(settings.get("SUPABASE_READ_ALLOWLIST", "")) if item["project_ref"] == project_ref]
                if not api_key.startswith("sb_publishable_") or not allowlist:
                    failures.append({"project_id": project.get("id"), "source_id": source_id, "status": "not_configured" if not api_key.startswith("sb_publishable_") or not settings.get("SUPABASE_READ_ALLOWLIST") else "no_tables_allowlisted"})
                    continue
                for entry in allowlist:
                    table_content, table_status, resolved_uri = _supabase_table(project_ref, entry, key=api_key)
                    doc = {"document_id": f"supabase:{project_ref}:{entry['table']}", "project_id": project.get("id"), "source_id": "supabase", "title": f"{project.get('name', project_ref)} — {entry['table']}", "uri": resolved_uri or uri, "content": table_content, "status": table_status}
                    if doc["status"] not in {"read", "partial"}:
                        failures.append({"project_id": project.get("id"), "source_id": source_id, "status": table_status, "table": entry["table"]})
                        continue
                    remaining = MAX_TOTAL_CHARS - total_chars
                    if remaining <= 0:
                        failures.append({"project_id": project.get("id"), "source_id": source_id, "status": "total_content_limit_reached"})
                        break
                    original_length = len(doc["content"])
                    doc["content"] = doc["content"][:min(MAX_DOCUMENT_CHARS, remaining)]
                    doc["truncated"] = doc["status"] == "partial" or len(doc["content"]) < original_length
                    if doc["truncated"]:
                        doc["status"] = "partial"
                    total_chars += len(doc["content"])
                    doc["content_sha256"] = hashlib.sha256(doc["content"].encode("utf-8")).hexdigest()
                    documents.append(doc)
                continue
            elif source_id == "cloudflare":
                parsed = urllib.parse.urlparse(uri)
                parts = [part for part in parsed.path.split("/") if part]
                account_id = settings.get("CLOUDFLARE_ACCOUNT_ID", "").strip()
                token = settings.get("CLOUDFLARE_API_TOKEN", "").strip()
                if parsed.scheme != "cloudflare" or parsed.netloc != "worker" or len(parts) != 1:
                    failures.append({"project_id": project.get("id"), "source_id": source_id, "status": "invalid_reference"})
                    continue
                script_name = parts[0]
                key = ("cloudflare", account_id + ":" + script_name)
                if key in seen:
                    continue
                seen.add(key)
                if not re.fullmatch(r"[a-fA-F0-9]{32}", account_id) or not token:
                    failures.append({"project_id": project.get("id"), "source_id": source_id, "status": "not_configured"})
                    continue
                text, status, resolved_uri = _cloudflare_worker(account_id, script_name, token=token)
                doc = {"document_id": f"cloudflare:{account_id}:{script_name}", "project_id": project.get("id"), "source_id": "cloudflare", "title": f"Cloudflare Worker {script_name}", "uri": resolved_uri or uri, "content": text, "status": status}
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
            "collector_credentials_in_output": False,
            "source_content_may_contain_embedded_secrets": True,
            "supabase_read_only_publishable_key": True,
            "supabase_table_allowlist_required": True,
            "cloudflare_workers_get_only": True,
            "content_sent_to_model": False,
        },
    }
