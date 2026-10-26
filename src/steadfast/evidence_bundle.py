from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

from .checks import evidence_findings, run_audit
from .code_truth import code_truth_report
from .docsync import docs_sync_report
from .findings import finding_metrics, list_findings
from .goals import goal_report
from .inventory import inventory_report
from .policy import load_policy
from .release import release_report
from .security import security_findings, workflow_findings
from .session_ledger import SessionLedgerError, session_report, verify_session_ledger
from .workcycle import cycle_history, cycle_status

BUNDLE_DIR = ".steadfast/artifacts"
MAX_BUNDLE_BYTES = 64 * 1024 * 1024
MAX_ENTRIES = 1000
_ALLOWED_ENTRIES = {"manifest.json", "evidence.json"}


class EvidenceBundleError(ValueError):
    """Raised when an evidence bundle cannot be safely built or verified."""


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _safe_output(repo: Path, relative: str) -> Path:
    candidate = Path(relative)
    if candidate.is_absolute() or ".." in candidate.parts or not relative.strip():
        raise EvidenceBundleError("output must be a repository-relative path")
    current = repo
    for part in candidate.parts[:-1]:
        current = current / part
        if current.exists() and current.is_symlink():
            raise EvidenceBundleError("output path may not traverse symlinks")
    path = repo / candidate
    if path.exists() and path.is_symlink():
        raise EvidenceBundleError("output file may not be a symlink")
    resolved_parent = path.parent.resolve()
    try:
        resolved_parent.relative_to(repo.resolve())
    except ValueError as exc:
        raise EvidenceBundleError("output path resolves outside repository") from exc
    return resolved_parent / path.name


def _commit(repo: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=5, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def _component(function: Any, *args: Any, **kwargs: Any) -> dict[str, Any]:
    try:
        value = function(*args, **kwargs)
        if isinstance(value, dict):
            return value
        return {"value": value}
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}", "available": False}


def collect_evidence(repo: Path) -> dict[str, Any]:
    """Collect structured, secret-minimized release and governance evidence."""
    root = repo.resolve()
    policy = load_policy(root)
    inventory = inventory_report(root)
    # Bundles are outputs, not product source. Excluding prior bundles avoids
    # recursive growth when a repository produces multiple evidence packages.
    inventory["files"] = [
        item for item in inventory.get("files", [])
        if not str(item.get("path", "")).startswith(BUNDLE_DIR + "/")
    ]
    inventory["file_count"] = len(inventory["files"])
    inventory["repository"] = root.name
    try:
        sessions = session_report(root, limit=100)
        ledger_integrity = verify_session_ledger(root)
    except SessionLedgerError as exc:
        sessions = {"ledger": ".steadfast/agent-sessions.jsonl", "integrity": "invalid",
                    "error": str(exc), "total_events": 0, "returned_events": 0,
                    "decisions": {}, "tools": {}, "sessions": [], "events": []}
        ledger_integrity = {"valid": False, "error": str(exc), "events_verified": 0}
    report = {
        "schema_version": 1,
        "product": "Steadfast",
        "generated_at": _now(),
        "repository": root.name,
        "commit": _commit(root),
        "scope": "metadata and verification results only; source file contents and raw secrets are not embedded",
        "components": {
            "audit": _component(run_audit, root),
            "security": _component(lambda: {"findings": security_findings(root, policy) + workflow_findings(root)}),
            "evidence": _component(lambda: {"findings": evidence_findings(root, policy)}),
            "goals": _component(goal_report, root, policy),
            "release": _component(release_report, root),
            "inventory": inventory,
            "documentation_contract": _component(docs_sync_report, root),
            "code_truth": _component(code_truth_report, root),
            "work_cycle": _component(cycle_status, root),
            "work_cycle_history": _component(cycle_history, root, 100),
            "agent_sessions": sessions,
            "agent_session_integrity": ledger_integrity,
            "finding_ledger": _component(list_findings, root, limit=1000),
            "finding_metrics": _component(finding_metrics, root),
        },
    }
    # Provide a compact, explicit outcome index without conflating unavailable
    # checks with passing checks.
    outcomes: dict[str, str] = {}
    for name, value in report["components"].items():
        if not isinstance(value, dict) or value.get("available") is False or "error" in value:
            outcomes[name] = "unavailable"
        elif value.get("passed") is False or value.get("ready") is False or value.get("valid") is False:
            outcomes[name] = "failed"
        elif name == "security" and any(x.get("severity") == "error" for x in value.get("findings", [])):
            outcomes[name] = "failed"
        elif name == "evidence" and any(x.get("severity") == "error" for x in value.get("findings", [])):
            outcomes[name] = "failed"
        else:
            outcomes[name] = "observed"
    report["outcomes"] = outcomes
    report["summary"] = {
        "components": len(outcomes),
        "failed": sum(value == "failed" for value in outcomes.values()),
        "unavailable": sum(value == "unavailable" for value in outcomes.values()),
        "observed": sum(value == "observed" for value in outcomes.values()),
        "release_ready": bool(report["components"].get("release", {}).get("ready", False)),
    }
    return report


def build_evidence_bundle(repo: Path, output: str | None = None, *, overwrite: bool = False) -> dict[str, Any]:
    root = repo.resolve()
    if not root.is_dir():
        raise EvidenceBundleError("repository root does not exist")
    if output is None:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        output = f"{BUNDLE_DIR}/steadfast-evidence-{stamp}.zip"
    destination = _safe_output(root, output)
    if destination.exists() and not overwrite:
        raise EvidenceBundleError(f"output already exists: {destination.relative_to(root).as_posix()} (use --overwrite to replace)")
    report = collect_evidence(root)
    report_bytes = json.dumps(report, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"
    manifest = {
        "schema_version": 1,
        "product": "Steadfast evidence bundle",
        "generated_at": report["generated_at"],
        "repository": root.name,
        "commit": report["commit"],
        "artifacts": {
            "evidence.json": {"sha256": hashlib.sha256(report_bytes).hexdigest(), "bytes": len(report_bytes)},
        },
        "integrity_note": "SHA-256 detects accidental or unauthorized content changes; this manifest is not a digital signature and does not authenticate who produced the bundle.",
    }
    manifest_bytes = json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=".steadfast-evidence-", suffix=".tmp", dir=destination.parent)
    os.close(fd)
    temporary = Path(temporary_name)
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            for name, data in (("manifest.json", manifest_bytes), ("evidence.json", report_bytes)):
                info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o600 << 16
                archive.writestr(info, data)
        if temporary.stat().st_size > MAX_BUNDLE_BYTES:
            raise EvidenceBundleError("generated bundle exceeds 64 MiB")
        if destination.exists() and not overwrite:
            raise EvidenceBundleError(f"output appeared during build: {destination.relative_to(root).as_posix()}")
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    return {
        "status": "built",
        "path": destination.relative_to(root).as_posix(),
        "bytes": destination.stat().st_size,
        "sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
        "summary": report["summary"],
        "commit": report["commit"],
    }


def verify_evidence_bundle(repo: Path, relative: str) -> dict[str, Any]:
    root = repo.resolve()
    path = _safe_output(root, relative)
    if not path.is_file() or path.is_symlink():
        raise EvidenceBundleError("bundle must be an existing regular file inside the repository")
    if path.stat().st_size > MAX_BUNDLE_BYTES:
        raise EvidenceBundleError("bundle exceeds 64 MiB")
    try:
        with zipfile.ZipFile(path, "r") as archive:
            infos = archive.infolist()
            if len(infos) > MAX_ENTRIES:
                raise EvidenceBundleError("bundle contains too many entries")
            names = [item.filename for item in infos]
            if len(names) != len(set(names)):
                raise EvidenceBundleError("bundle contains duplicate entry names")
            for name in names:
                member = PurePosixPath(name)
                if member.is_absolute() or ".." in member.parts or name not in _ALLOWED_ENTRIES:
                    raise EvidenceBundleError(f"unsafe or unexpected bundle entry: {name!r}")
            if set(names) != _ALLOWED_ENTRIES:
                raise EvidenceBundleError("bundle must contain exactly manifest.json and evidence.json")
            if sum(item.file_size for item in infos) > MAX_BUNDLE_BYTES:
                raise EvidenceBundleError("uncompressed bundle exceeds 64 MiB")
            manifest = json.loads(archive.read("manifest.json"))
            evidence_bytes = archive.read("evidence.json")
    except (OSError, zipfile.BadZipFile, RuntimeError, json.JSONDecodeError, KeyError) as exc:
        raise EvidenceBundleError(f"bundle cannot be read: {exc}") from exc
    if not isinstance(manifest, dict) or manifest.get("schema_version") != 1:
        raise EvidenceBundleError("unsupported bundle manifest schema")
    artifact = manifest.get("artifacts", {}).get("evidence.json", {})
    actual_hash = hashlib.sha256(evidence_bytes).hexdigest()
    if artifact.get("sha256") != actual_hash or artifact.get("bytes") != len(evidence_bytes):
        raise EvidenceBundleError("evidence.json checksum or size does not match manifest")
    try:
        evidence = json.loads(evidence_bytes)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise EvidenceBundleError(f"evidence payload is invalid JSON: {exc}") from exc
    if not isinstance(evidence, dict) or evidence.get("schema_version") != 1:
        raise EvidenceBundleError("unsupported evidence payload schema")
    return {
        "valid": True,
        "path": path.relative_to(root).as_posix(),
        "bundle_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "commit": manifest.get("commit", ""),
        "generated_at": manifest.get("generated_at", ""),
        "summary": evidence.get("summary", {}),
        "components": sorted(evidence.get("components", {})),
    }
