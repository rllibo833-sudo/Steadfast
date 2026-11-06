from __future__ import annotations

import os
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Mapping


def _request_json(url: str, *, token: str, headers: Mapping[str, str] | None = None) -> dict[str, Any]:
    request_headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    request_headers.update(dict(headers or {}))
    request = urllib.request.Request(url, headers=request_headers, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=12) as response:
            import json
            payload = json.loads(response.read().decode("utf-8"))
            return payload if isinstance(payload, dict) else {"_value": payload}
    except urllib.error.HTTPError as exc:
        return {"_http_status": exc.code}
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return {"_unreachable": True}


def _page_id(uri: str) -> str | None:
    parsed = urllib.parse.urlparse(uri)
    raw = parsed.path.rstrip("/").split("/")[-1]
    candidate = re.sub(r"[^0-9a-fA-F]", "", raw)
    return candidate if len(candidate) == 32 else None


def _notion_report(manifest: dict[str, Any], env: Mapping[str, str]) -> dict[str, Any]:
    token = env.get("NOTION_API_TOKEN", "").strip()
    refs = []
    for project in manifest.get("projects", []):
        if not isinstance(project, dict):
            continue
        for ref in project.get("sources", []) if isinstance(project.get("sources"), list) else []:
            if isinstance(ref, dict) and ref.get("source_id") == "notion":
                refs.append({"project_id": project.get("id"), "uri": ref.get("uri"), "title": ref.get("title")})
    if not token:
        return {"source": "notion", "status": "not_configured", "checked": 0, "items": []}
    items = []
    for ref in refs:
        page_id = _page_id(str(ref.get("uri", "")))
        if not page_id:
            items.append({"project_id": ref.get("project_id"), "status": "invalid_reference"})
            continue
        payload = _request_json(
            f"https://api.notion.com/v1/pages/{page_id}",
            token=token,
            headers={"Notion-Version": "2022-06-28"},
        )
        status = "reachable"
        if payload.get("_http_status") == 404:
            status = "not_found_or_not_shared"
        elif payload.get("_http_status") in (401, 403):
            status = "unauthorized"
        elif payload.get("_unreachable"):
            status = "unreachable"
        elif payload.get("archived") or payload.get("in_trash"):
            status = "archived"
        elif not payload.get("id"):
            status = "invalid_response"
        items.append({
            "project_id": ref.get("project_id"),
            "page_id": page_id,
            "manifest_title": ref.get("title"),
            "status": status,
            "last_edited_time": payload.get("last_edited_time"),
        })
    statuses = {item["status"] for item in items}
    overall = "connected" if items and statuses <= {"reachable", "archived"} else "degraded" if items else "connected"
    return {"source": "notion", "status": overall, "checked": len(items), "items": items}


def _supabase_report(manifest: dict[str, Any], env: Mapping[str, str]) -> dict[str, Any]:
    token = env.get("SUPABASE_ACCESS_TOKEN", "").strip()
    refs = set()
    for project in manifest.get("projects", []):
        if not isinstance(project, dict):
            continue
        for ref in project.get("sources", []) if isinstance(project.get("sources"), list) else []:
            if isinstance(ref, dict) and ref.get("source_id") == "supabase":
                match = re.search(r"supabase://project/([a-z0-9]+)", str(ref.get("uri", "")))
                if match:
                    refs.add(match.group(1))
    if not token:
        return {"source": "supabase", "status": "not_configured", "checked": 0, "items": []}
    items = []
    for project_ref in sorted(refs):
        payload = _request_json(f"https://api.supabase.com/v1/projects/{project_ref}", token=token)
        if payload.get("_http_status") == 404:
            status = "not_found_or_not_authorized"
        elif payload.get("_http_status") in (401, 403):
            status = "unauthorized"
        elif payload.get("_unreachable"):
            status = "unreachable"
        elif payload.get("status") == "INACTIVE":
            status = "inactive"
        elif payload.get("id"):
            status = "active"
        else:
            status = "invalid_response"
        items.append({"project_ref": project_ref, "status": status, "region": payload.get("region")})
    statuses = {item["status"] for item in items}
    overall = "connected" if statuses <= {"active", "inactive"} else "degraded"
    return {"source": "supabase", "status": overall, "checked": len(items), "items": items}


def _cloudflare_report(env: Mapping[str, str]) -> dict[str, Any]:
    token = env.get("CLOUDFLARE_API_TOKEN", "").strip()
    account_id = env.get("CLOUDFLARE_ACCOUNT_ID", "").strip()
    if not token or not account_id:
        return {"source": "cloudflare", "status": "not_configured", "checked": 0, "items": []}
    payload = _request_json(
        f"https://api.cloudflare.com/client/v4/accounts/{urllib.parse.quote(account_id)}/workers/scripts",
        token=token,
    )
    if payload.get("_http_status") in (401, 403):
        status = "unauthorized"
    elif payload.get("_unreachable"):
        status = "unreachable"
    elif payload.get("success") is True:
        status = "connected"
    else:
        status = "invalid_response"
    scripts = payload.get("result", []) if isinstance(payload.get("result"), list) else []
    return {
        "source": "cloudflare",
        "status": status,
        "checked": 1,
        "items": [{"worker_name": item.get("id")} for item in scripts if isinstance(item, dict) and isinstance(item.get("id"), str)],
    }


def _termux_report(repo: Path, env: Mapping[str, str]) -> dict[str, Any]:
    root_value = env.get("JBF_ROOT") or str(Path.home() / "JBF")
    root = Path(root_value).expanduser().resolve()
    if not root.is_dir():
        return {"source": "termux", "status": "not_found", "checked": 0, "items": [], "root": str(root)}
    expected = ("Cargo.toml", "device/profile.toml", "modules/catalog")
    present = [item for item in expected if (root / item).exists()]
    return {
        "source": "termux",
        "status": "reachable" if len(present) == len(expected) else "partial" if present else "not_found",
        "checked": len(expected),
        "items": [{"path": item, "present": item in present} for item in expected],
        "root": str(root),
        "note": "Local filesystem metadata only; no device commands are executed.",
    }


def source_report(
    manifest: dict[str, Any],
    *,
    repo: Path | str = ".",
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Probe source metadata with GET-only requests; never write to remote or local sources."""
    settings = os.environ if env is None else env
    reports = [
        _notion_report(manifest, settings),
        _supabase_report(manifest, settings),
        _cloudflare_report(settings),
        _termux_report(Path(repo), settings),
    ]
    errors = sum(
        item.get("status") in {"unauthorized", "unreachable", "invalid_response", "degraded"}
        for item in reports
    )
    return {
        "schema_version": "1.0.0",
        "check": "universe-source-probes",
        "sources": reports,
        "summary": {
            "sources": len(reports),
            "connected": sum(item["status"] in {"connected", "reachable"} for item in reports),
            "not_configured": sum(item["status"] == "not_configured" for item in reports),
            "errors": errors,
        },
        "safety": {
            "http_method": "GET",
            "remote_writes": False,
            "local_files_modified": False,
            "commands_executed": False,
            "credentials_in_output": False,
        },
    }
