from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


def _finding(code: str, severity: str, path: str, message: str) -> dict[str, str]:
    return {"code": code, "severity": severity, "path": path, "message": message}


def load_universe_manifest(path: Path) -> tuple[dict[str, Any] | None, list[dict[str, str]]]:
    """Load a JSON ecosystem manifest without executing or fetching referenced sources."""
    findings: list[dict[str, str]] = []
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        return None, [_finding("UNIVERSE_READ_ERROR", "error", str(path), str(exc))]
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        return None, [_finding("UNIVERSE_INVALID_JSON", "error", str(path), f"Line {exc.lineno}: {exc.msg}")]
    if not isinstance(value, dict):
        return None, [_finding("UNIVERSE_ROOT_TYPE", "error", str(path), "Manifest root must be a JSON object.")]
    return value, findings


def audit_universe_manifest(manifest: dict[str, Any], manifest_path: Path) -> dict[str, Any]:
    """Validate manifest structure, identifiers, references and local source availability.

    Remote URLs are syntax-checked only. No network calls or source commands are executed.
    """
    findings: list[dict[str, str]] = []
    required_top = ("manifest_version", "universe_id", "sources", "projects", "relationships")
    for key in required_top:
        if key not in manifest:
            findings.append(_finding("UNIVERSE_REQUIRED_FIELD", "error", key, f"Missing required field: {key}"))

    sources = manifest.get("sources", [])
    projects = manifest.get("projects", [])
    relationships = manifest.get("relationships", [])
    if not isinstance(sources, list):
        findings.append(_finding("UNIVERSE_SOURCES_TYPE", "error", "sources", "sources must be an array."))
        sources = []
    if not isinstance(projects, list):
        findings.append(_finding("UNIVERSE_PROJECTS_TYPE", "error", "projects", "projects must be an array."))
        projects = []
    if not isinstance(relationships, list):
        findings.append(_finding("UNIVERSE_RELATIONSHIPS_TYPE", "error", "relationships", "relationships must be an array."))
        relationships = []

    source_ids: set[str] = set()
    for index, source in enumerate(sources):
        location = f"sources[{index}]"
        if not isinstance(source, dict):
            findings.append(_finding("UNIVERSE_SOURCE_TYPE", "error", location, "Source entry must be an object."))
            continue
        source_id = source.get("id")
        if not isinstance(source_id, str) or not source_id.strip():
            findings.append(_finding("UNIVERSE_SOURCE_ID", "error", location, "Source id must be a non-empty string."))
        elif source_id in source_ids:
            findings.append(_finding("UNIVERSE_DUPLICATE_SOURCE", "error", location, f"Duplicate source id: {source_id}"))
        else:
            source_ids.add(source_id)

    project_ids: set[str] = set()
    source_ref_count = 0
    for index, project in enumerate(projects):
        location = f"projects[{index}]"
        if not isinstance(project, dict):
            findings.append(_finding("UNIVERSE_PROJECT_TYPE", "error", location, "Project entry must be an object."))
            continue
        project_id = project.get("id")
        if not isinstance(project_id, str) or not project_id.strip():
            findings.append(_finding("UNIVERSE_PROJECT_ID", "error", location, "Project id must be a non-empty string."))
        elif project_id in project_ids:
            findings.append(_finding("UNIVERSE_DUPLICATE_PROJECT", "error", location, f"Duplicate project id: {project_id}"))
        else:
            project_ids.add(project_id)

        refs = project.get("sources", [])
        if not isinstance(refs, list):
            findings.append(_finding("UNIVERSE_PROJECT_SOURCES_TYPE", "error", f"{location}.sources", "Project sources must be an array."))
            continue
        for ref_index, ref in enumerate(refs):
            source_ref_count += 1
            ref_path = f"{location}.sources[{ref_index}]"
            if not isinstance(ref, dict):
                findings.append(_finding("UNIVERSE_SOURCE_REF_TYPE", "error", ref_path, "Source reference must be an object."))
                continue
            source_id = ref.get("source_id")
            uri = ref.get("uri")
            if source_id not in source_ids:
                findings.append(_finding("UNIVERSE_UNKNOWN_SOURCE", "error", ref_path, f"Unknown source_id: {source_id!r}"))
            if not isinstance(uri, str) or not uri.strip():
                findings.append(_finding("UNIVERSE_SOURCE_URI", "error", ref_path, "Source reference requires a non-empty uri."))
                continue
            parsed = urlparse(uri)
            if parsed.scheme in {"http", "https"}:
                if not parsed.netloc:
                    findings.append(_finding("UNIVERSE_INVALID_URL", "error", ref_path, "HTTP source URL has no host."))
                # Remote source reachability is intentionally not checked here.
            elif parsed.scheme == "local":
                local_value = (parsed.netloc + parsed.path).lstrip("/")
                candidate = (manifest_path.parent.parent / local_value).resolve()
                if not candidate.exists():
                    findings.append(_finding("UNIVERSE_LOCAL_SOURCE_MISSING", "warning", ref_path, f"Local source is not present relative to index root: {local_value}"))
            elif parsed.scheme not in {"supabase", "notion", "github"}:
                findings.append(_finding("UNIVERSE_URI_SCHEME", "warning", ref_path, f"Unrecognized source URI scheme: {parsed.scheme or '(none)'}"))

    for index, edge in enumerate(relationships):
        location = f"relationships[{index}]"
        if not isinstance(edge, dict):
            findings.append(_finding("UNIVERSE_RELATIONSHIP_TYPE", "error", location, "Relationship must be an object."))
            continue
        for endpoint in ("from", "to"):
            node = edge.get(endpoint)
            if node not in project_ids and node not in {"harness", "ncm"}:
                findings.append(_finding("UNIVERSE_UNKNOWN_ENDPOINT", "error", f"{location}.{endpoint}", f"Unknown relationship endpoint: {node!r}"))

    errors = sum(item["severity"] == "error" for item in findings)
    warnings = sum(item["severity"] == "warning" for item in findings)
    return {
        "schema_version": 1,
        "check": "universe-manifest",
        "manifest": str(manifest_path),
        "status": "failed" if errors else "review_required" if warnings else "passed",
        "passed": errors == 0,
        "summary": {
            "projects": len(projects),
            "sources": len(sources),
            "source_references": source_ref_count,
            "relationships": len(relationships),
            "errors": errors,
            "warnings": warnings,
        },
        "findings": findings,
        "safety": {
            "network_requests_made": False,
            "commands_executed": False,
            "remote_references": "syntax_checked_only",
            "project_files_modified": False,
        },
    }


def universe_report(repo: Path, manifest_argument: str = "ecosystem/universe.json") -> dict[str, Any]:
    root = repo.resolve()
    manifest_path = Path(manifest_argument)
    if not manifest_path.is_absolute():
        manifest_path = root / manifest_path
    manifest, load_findings = load_universe_manifest(manifest_path)
    if manifest is None:
        return {
            "schema_version": 1,
            "check": "universe-manifest",
            "manifest": str(manifest_path),
            "status": "failed",
            "passed": False,
            "summary": {"projects": 0, "sources": 0, "source_references": 0, "relationships": 0, "errors": len(load_findings), "warnings": 0},
            "findings": load_findings,
            "safety": {"network_requests_made": False, "commands_executed": False, "project_files_modified": False},
        }
    return audit_universe_manifest(manifest, manifest_path)
