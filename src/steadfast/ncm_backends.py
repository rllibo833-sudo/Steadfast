from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Mapping
from urllib.parse import urlparse


def probe_backend_services(
    manifest: Mapping[str, Any], *, timeout: float = 8.0
) -> dict[str, Any]:
    """Read-only probes for explicitly declared Supabase Edge Function endpoints.

    A 401/403 is recorded as reachable-but-authenticated, never as healthy application
    execution. No credentials, writes, user data, or database mutations are performed.
    """
    declarations = manifest.get("backend_services", [])
    if not isinstance(declarations, list):
        declarations = []
    results: list[dict[str, Any]] = []

    for item in declarations:
        if not isinstance(item, dict):
            continue
        project_id = item.get("project_id")
        service_id = item.get("id")
        endpoint = item.get("endpoint")
        if not all(isinstance(value, str) and value.strip() for value in (project_id, service_id, endpoint)):
            results.append({
                "project_id": project_id if isinstance(project_id, str) else None,
                "service_id": service_id if isinstance(service_id, str) else None,
                "status": "failed",
                "findings": [{"code": "BACKEND_PROBE_DECLARATION_INVALID"}],
            })
            continue

        parsed = urlparse(endpoint)
        if parsed.scheme != "https" or not (parsed.hostname or "").endswith(".supabase.co") or not parsed.path.startswith("/functions/v1/"):
            results.append({
                "project_id": project_id, "service_id": service_id, "status": "failed",
                "findings": [{"code": "BACKEND_PROBE_ENDPOINT_NOT_ALLOWLISTED"}],
            })
            continue

        request = urllib.request.Request(
            endpoint,
            headers={"Accept": "application/json, text/html", "User-Agent": "Steadfast-NCM-readonly-probe/1.0"},
            method="GET",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                status_code = response.status
                body = response.read(4096).decode("utf-8", errors="replace")
                content_type = response.headers.get("Content-Type", "")
        except urllib.error.HTTPError as exc:
            status_code = exc.code
            body = exc.read(4096).decode("utf-8", errors="replace")
            content_type = exc.headers.get("Content-Type", "") if exc.headers else ""
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            results.append({
                "project_id": project_id, "service_id": service_id, "endpoint": endpoint,
                "status": "failed",
                "findings": [{"code": "BACKEND_ENDPOINT_UNREACHABLE", "error_type": type(exc).__name__}],
            })
            continue

        expected = item.get("expected_status", [200])
        if not isinstance(expected, list):
            expected = [200]
        auth_required = status_code in {401, 403} and item.get("auth_mode") == "required"
        if status_code in expected:
            state = "ready"
        elif auth_required:
            state = "reachable_auth_required"
        else:
            state = "failed"

        results.append({
            "project_id": project_id,
            "service_id": service_id,
            "endpoint": endpoint,
            "http_status": status_code,
            "status": state,
            "auth_mode": item.get("auth_mode", "unknown"),
            "content_type": content_type,
            "response_excerpt": body[:240] if state == "ready" else None,
            "findings": [] if state != "failed" else [{"code": "BACKEND_ENDPOINT_UNEXPECTED_STATUS"}],
        })

    summary = {
        "services": len(results),
        "ready": sum(item["status"] == "ready" for item in results),
        "reachable_auth_required": sum(item["status"] == "reachable_auth_required" for item in results),
        "failed": sum(item["status"] == "failed" for item in results),
    }
    return {
        "status": "completed" if summary["failed"] == 0 else "partial",
        "summary": summary,
        "results": results,
        "safety": {"read_only": True, "credentials_sent": False, "database_writes": False},
    }


__all__ = ["probe_backend_services"]
