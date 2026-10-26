from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .checks import run_audit
from .goals import goal_report
from .policy import load_policy
from .release import release_report
from .security import security_findings, workflow_findings

STATE_PATH = ".steadfast/finding-ledger.json"
JOURNAL_PATH = ".steadfast/finding-events.jsonl"
MAX_LEDGER_BYTES = 16 * 1024 * 1024
VALID_STATES = {"open", "triaged", "accepted", "fixed", "false_positive"}
VALID_PRIORITIES = {"critical", "high", "medium", "low"}


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def fingerprint(finding: dict[str, Any]) -> str:
    """Stable identifier that ignores changing prose and scan timestamps."""
    identity = {
        "code": str(finding.get("code", "UNKNOWN")),
        "path": str(finding.get("path", "")).replace("\\", "/"),
        "rule": str(finding.get("rule", "")),
        "symbol": str(finding.get("symbol", "")),
    }
    return hashlib.sha256(_canonical(identity)).hexdigest()[:20]


def _severity_priority(severity: str) -> str:
    return {"critical": "critical", "error": "high", "warning": "medium", "info": "low"}.get(
        severity.lower(), "medium"
    )


def _safe_repo_path(repo: Path, value: str) -> Path:
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("path must be repository-relative")
    resolved = (repo / path).resolve()
    try:
        resolved.relative_to(repo.resolve())
    except ValueError as exc:
        raise ValueError("path escapes repository") from exc
    return resolved


def _read_ledger(repo: Path) -> dict[str, Any]:
    path = repo / STATE_PATH
    if not path.exists():
        return {"schema_version": 1, "updated_at": _now(), "findings": {}}
    if path.is_symlink() or path.stat().st_size > MAX_LEDGER_BYTES:
        raise ValueError("finding ledger is unsafe or exceeds 16 MiB")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"finding ledger cannot be read: {exc}") from exc
    if not isinstance(value, dict) or value.get("schema_version") != 1 or not isinstance(value.get("findings"), dict):
        raise ValueError("unsupported or malformed finding ledger")
    for key, item in value["findings"].items():
        if not isinstance(item, dict) or item.get("state") not in VALID_STATES:
            raise ValueError(f"invalid ledger entry {key!r}")
    return value


def _validate_journal(repo: Path) -> tuple[list[dict[str, Any]], str]:
    path = repo / JOURNAL_PATH
    if not path.exists():
        return [], "0" * 64
    if path.is_symlink() or path.stat().st_size > MAX_LEDGER_BYTES:
        raise ValueError("finding journal is unsafe or exceeds 16 MiB")
    records, previous = [], "0" * 64
    try:
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            record = json.loads(line)
            digest = record.pop("hash", None)
            if record.get("previous_hash") != previous:
                raise ValueError(f"finding journal chain invalid at line {number}")
            expected = hashlib.sha256(previous.encode() + _canonical(record)).hexdigest()
            if digest != expected:
                raise ValueError(f"finding journal hash invalid at line {number}")
            record["hash"] = digest
            records.append(record)
            previous = digest
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"finding journal cannot be read: {exc}") from exc
    return records, previous


def _event(repo: Path, event: str, finding_id: str, details: dict[str, Any]) -> dict[str, Any]:
    path = repo / JOURNAL_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    records, previous = _validate_journal(repo)
    record = {
        "sequence": len(records) + 1,
        "at": _now(),
        "event": event,
        "finding_id": finding_id,
        "details": details,
        "previous_hash": previous,
    }
    digest = hashlib.sha256(previous.encode() + _canonical(record)).hexdigest()
    record["hash"] = digest
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        payload = (json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n").encode()
        if os.write(fd, payload) != len(payload):
            raise OSError("short write to finding journal")
    finally:
        os.close(fd)
    return record


def _save_ledger(repo: Path, ledger: dict[str, Any]) -> None:
    ledger["updated_at"] = _now()
    path = repo / STATE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps(ledger, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temp.replace(path)


def _collect(repo: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    policy = load_policy(repo)
    audit = run_audit(repo)
    goals = goal_report(repo, policy)
    release = release_report(repo)
    security = security_findings(repo, policy) + workflow_findings(repo)
    raw: list[dict[str, Any]] = []
    raw.extend(audit.get("findings", []))
    raw.extend(goals.get("findings", []))
    raw.extend(security)
    # De-duplicate findings surfaced by more than one report without erasing provenance.
    merged: dict[str, dict[str, Any]] = {}
    for finding in raw:
        item = dict(finding)
        fid = fingerprint(item)
        if fid in merged:
            sources = set(merged[fid].get("sources", []))
            sources.add("governance")
            merged[fid]["sources"] = sorted(sources)
            continue
        item["id"] = fid
        item["priority"] = _severity_priority(str(item.get("severity", "warning")))
        item["sources"] = ["audit"]
        merged[fid] = item
    return sorted(merged.values(), key=lambda x: ({"critical": 0, "high": 1, "medium": 2, "low": 3}[x["priority"]], x["path"], x["code"])), {
        "audit_passed": bool(audit.get("passed")),
        "audit_summary": audit.get("summary", {}),
        "product_code_lines": audit.get("product_code_lines", 0),
        "product_code_budget": audit.get("product_code_budget", 0),
        "release_ready": bool(release.get("ready")),
        "release_blockers": release.get("blockers", []),
    }


def scan_findings(repo: Path) -> dict[str, Any]:
    """Refresh live findings while preserving triage and closure history."""
    repo = repo.resolve()
    current, summary = _collect(repo)
    ledger = _read_ledger(repo)
    existing = ledger["findings"]
    seen: set[str] = set()
    opened = reopened = unchanged = 0
    for raw in current:
        fid = raw["id"]
        seen.add(fid)
        old = existing.get(fid)
        if old is None:
            old = {
                **raw, "state": "open", "owner": "", "due_date": None, "resolution": "",
                "created_at": _now(), "updated_at": _now(), "last_seen_at": _now(),
                "first_seen_scan": ledger.get("scan_count", 0) + 1, "last_seen_scan": ledger.get("scan_count", 0) + 1,
            }
            existing[fid] = old
            opened += 1
            _event(repo, "finding_opened", fid, {"code": raw["code"], "path": raw["path"], "priority": raw["priority"]})
            continue
        if old["state"] in {"fixed", "false_positive"}:
            old["state"] = "open"
            old["resolution"] = ""
            reopened += 1
            _event(repo, "finding_reopened", fid, {"code": raw["code"], "path": raw["path"]})
        else:
            unchanged += 1
        # Refresh live facts only; preserve user triage metadata.
        for key in ("severity", "code", "path", "message", "priority", "sources"):
            if key in raw:
                old[key] = raw[key]
        old["last_seen_at"] = _now()
        old["last_seen_scan"] = ledger.get("scan_count", 0) + 1
        old["updated_at"] = _now()
    disappeared = []
    for fid, item in existing.items():
        if fid not in seen and item["state"] not in {"fixed", "false_positive"}:
            item["state"] = "fixed"
            item["resolution"] = "No longer reported by the latest governance scan"
            item["updated_at"] = _now()
            item["resolved_at"] = _now()
            disappeared.append(fid)
            _event(repo, "finding_auto_resolved", fid, {"code": item.get("code"), "path": item.get("path")})
    ledger["scan_count"] = int(ledger.get("scan_count", 0)) + 1
    ledger["last_scan_at"] = _now()
    ledger["last_scan_summary"] = summary
    _save_ledger(repo, ledger)
    return {
        "ledger": STATE_PATH, "journal": JOURNAL_PATH, "scan_count": ledger["scan_count"],
        "live_count": len(current), "opened": opened, "reopened": reopened,
        "unchanged": unchanged, "auto_resolved": len(disappeared),
        "summary": summary, "findings": list(existing.values()),
    }


def list_findings(
    repo: Path, state: str = "all", priority: str = "all", query: str = "", limit: int = 200
) -> dict[str, Any]:
    if state != "all" and state not in VALID_STATES:
        raise ValueError(f"state must be all or one of {sorted(VALID_STATES)}")
    if priority != "all" and priority not in VALID_PRIORITIES:
        raise ValueError(f"priority must be all or one of {sorted(VALID_PRIORITIES)}")
    if not 1 <= limit <= 1000:
        raise ValueError("limit must be from 1 to 1000")
    ledger = _read_ledger(repo.resolve())
    q = query.casefold().strip()
    items = []
    for item in ledger["findings"].values():
        if state != "all" and item["state"] != state:
            continue
        if priority != "all" and item.get("priority") != priority:
            continue
        haystack = " ".join(str(item.get(k, "")) for k in ("id", "code", "path", "message", "owner", "resolution"))
        if q and q not in haystack.casefold():
            continue
        items.append(item)
    order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    items.sort(key=lambda x: (x["state"] in {"fixed", "false_positive"}, order.get(x.get("priority", "medium"), 2), x.get("due_date") or "9999-12-31", x.get("path", "")))
    return {"count": len(items), "findings": items[:limit], "scan_count": ledger.get("scan_count", 0), "last_scan_at": ledger.get("last_scan_at")}


def triage_finding(
    repo: Path, finding_id: str, state: str | None = None, owner: str | None = None,
    priority: str | None = None, due_date: str | None = None, note: str = "",
) -> dict[str, Any]:
    repo = repo.resolve()
    if state is not None and state not in {"open", "triaged", "accepted"}:
        raise ValueError("triage state must be open, triaged, or accepted; use resolve for closure")
    if priority is not None and priority not in VALID_PRIORITIES:
        raise ValueError(f"priority must be one of {sorted(VALID_PRIORITIES)}")
    if owner is not None and (len(owner) > 200 or "\n" in owner or "\r" in owner):
        raise ValueError("owner must be a single line of at most 200 characters")
    if due_date:
        try:
            parsed = date.fromisoformat(due_date)
        except ValueError as exc:
            raise ValueError("due date must use YYYY-MM-DD") from exc
        if parsed < date.today():
            raise ValueError("due date cannot be in the past")
    ledger = _read_ledger(repo)
    item = ledger["findings"].get(finding_id)
    if item is None:
        raise ValueError(f"finding {finding_id!r} not found; run findings scan first")
    before = {key: item.get(key) for key in ("state", "owner", "priority", "due_date")}
    if state is not None:
        item["state"] = state
    if owner is not None:
        item["owner"] = owner.strip()
    if priority is not None:
        item["priority"] = priority
    if due_date is not None:
        item["due_date"] = due_date or None
    item["updated_at"] = _now()
    _event(repo, "finding_triaged", finding_id, {"before": before, "after": {key: item.get(key) for key in before}, "note": note[:2000]})
    _save_ledger(repo, ledger)
    return item


def resolve_finding(repo: Path, finding_id: str, resolution: str, false_positive: bool = False) -> dict[str, Any]:
    repo = repo.resolve()
    if not resolution.strip() or len(resolution) > 2000:
        raise ValueError("resolution must contain 1-2000 characters")
    ledger = _read_ledger(repo)
    item = ledger["findings"].get(finding_id)
    if item is None:
        raise ValueError(f"finding {finding_id!r} not found")
    if item["state"] in {"fixed", "false_positive"}:
        raise ValueError("finding is already resolved")
    item["state"] = "false_positive" if false_positive else "fixed"
    item["resolution"] = resolution.strip()
    item["updated_at"] = _now()
    item["resolved_at"] = _now()
    _event(repo, "finding_resolved", finding_id, {"state": item["state"], "resolution": item["resolution"]})
    _save_ledger(repo, ledger)
    return item


def finding_history(repo: Path, finding_id: str = "", limit: int = 100) -> dict[str, Any]:
    if not 1 <= limit <= 1000:
        raise ValueError("limit must be from 1 to 1000")
    records, _ = _validate_journal(repo.resolve())
    if finding_id:
        records = [item for item in records if item.get("finding_id") == finding_id]
    return {"count": min(len(records), limit), "events": list(reversed(records[-limit:])), "journal": JOURNAL_PATH}


def finding_metrics(repo: Path) -> dict[str, Any]:
    ledger = _read_ledger(repo.resolve())
    items = list(ledger["findings"].values())
    by_state = {state: sum(x.get("state") == state for x in items) for state in sorted(VALID_STATES)}
    by_priority = {priority: sum(x.get("priority") == priority and x.get("state") not in {"fixed", "false_positive"} for x in items) for priority in ("critical", "high", "medium", "low")}
    overdue = [x for x in items if x.get("due_date") and x["due_date"] < date.today().isoformat() and x["state"] not in {"fixed", "false_positive"}]
    accepted = [x for x in items if x.get("state") == "accepted"]
    return {
        "total": len(items), "by_state": by_state, "open_by_priority": by_priority,
        "overdue": len(overdue), "overdue_findings": overdue,
        "accepted_risk": len(accepted), "scan_count": ledger.get("scan_count", 0),
        "last_scan_at": ledger.get("last_scan_at"),
    }
