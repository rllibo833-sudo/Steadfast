from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .integrations import _shell_command, _tool_paths

LEDGER = ".steadfast/agent-sessions.jsonl"
MAX_BYTES = 32 * 1024 * 1024
MAX_RECORDS = 100_000
SENSITIVE = re.compile(r"(token|secret|password|passwd|api[_-]?key|authorization|cookie|credential)", re.I)


class SessionLedgerError(ValueError):
    """Raised when the durable agent session ledger is invalid or unsafe."""


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _canonical(record: dict[str, Any]) -> bytes:
    return json.dumps(record, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _event_name(event: dict[str, Any]) -> str:
    value = event.get("hook_event_name", event.get("event", event.get("type", "unknown")))
    return str(value).strip().casefold()[:80] or "unknown"


def _session_id(event: dict[str, Any]) -> str:
    for key in ("session_id", "sessionId", "conversation_id", "conversationId", "thread_id"):
        value = event.get(key)
        if isinstance(value, (str, int)) and str(value).strip():
            return str(value).strip()[:160]
    return "default"


def _tool_name(event: dict[str, Any]) -> str:
    for key in ("tool_name", "toolName", "name", "tool"):
        value = event.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()[:100]
    return "unknown"


def _redact(value: Any, depth: int = 0) -> Any:
    if depth > 5:
        return "[depth-limited]"
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, child in list(value.items())[:100]:
            name = str(key)[:100]
            if SENSITIVE.search(name):
                out[name] = "[REDACTED]"
            elif name.casefold() in {"command", "cmd", "script"} and isinstance(child, str):
                out[name] = _safe_command_preview(child)
            else:
                out[name] = _redact(child, depth + 1)
        return out
    if isinstance(value, list):
        return [_redact(item, depth + 1) for item in value[:100]]
    if isinstance(value, str):
        return value[:2000]
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return str(value)[:200]


def _safe_command_preview(command: str) -> str:
    value = command[:240]
    value = re.sub(r"(?i)(\b(?:token|secret|password|passwd|api[_-]?key|authorization)\s*[=:]\s*)([^\s;&|]+)", r"\1[REDACTED]", value)
    value = re.sub(r"(?i)(--(?:token|secret|password|passwd|api[_-]?key|authorization)\s+)([^\s;&|]+)", r"\1[REDACTED]", value)
    value = re.sub(r"(?i)(bearer\s+)[A-Za-z0-9._~+/-]+=*", r"\1[REDACTED]", value)
    return value


def _event_record(event: dict[str, Any], decision: dict[str, Any], session_id: str | None = None) -> dict[str, Any]:
    command = _shell_command(event)
    paths = []
    for raw in _tool_paths(event):
        paths.append(str(raw)[:500])
    tool_input = event.get("tool_input", event.get("input", {}))
    tool_result = event.get("tool_response", event.get("tool_result", event.get("response")))
    return {
        "event_id": uuid.uuid4().hex,
        "at": _now(),
        "session_id": session_id or _session_id(event),
        "event_name": _event_name(event),
        "tool_name": _tool_name(event),
        "decision": str(decision.get("decision", "block")),
        "finding_codes": [str(item.get("code", ""))[:100] for item in decision.get("findings", []) if isinstance(item, dict)][:50],
        "paths": list(dict.fromkeys(paths))[:100],
        "command_sha256": hashlib.sha256(command.encode("utf-8", errors="replace")).hexdigest() if command else "",
        "command_preview": _safe_command_preview(command) if command else "",
        "input_summary": _redact(tool_input) if isinstance(tool_input, dict) else {},
        "result_summary": _redact(tool_result) if isinstance(tool_result, (dict, list, str, int, float, bool)) else None,
        "work_cycle": _redact(decision.get("work_cycle", {})),
    }


def _read_records(repo: Path) -> list[dict[str, Any]]:
    path = repo / LEDGER
    if not path.exists():
        return []
    if path.is_symlink() or path.stat().st_size > MAX_BYTES:
        raise SessionLedgerError("agent session ledger is a symlink or exceeds 32 MiB")
    records: list[dict[str, Any]] = []
    previous = "0" * 64
    try:
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if number > MAX_RECORDS:
                raise SessionLedgerError("agent session ledger exceeds record limit")
            record = json.loads(line)
            if not isinstance(record, dict):
                raise SessionLedgerError(f"invalid ledger record at line {number}")
            digest = record.pop("hash", None)
            if record.get("sequence") != number or record.get("previous_hash") != previous:
                raise SessionLedgerError(f"ledger sequence/hash link invalid at line {number}")
            expected = hashlib.sha256((previous + _canonical(record).decode("utf-8")).encode("utf-8")).hexdigest()
            if digest != expected:
                raise SessionLedgerError(f"ledger hash invalid at line {number}")
            record["hash"] = digest
            previous = digest
            records.append(record)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SessionLedgerError(f"cannot read agent session ledger: {exc}") from exc
    return records


def record_agent_event(repo: Path, event: dict[str, Any], decision: dict[str, Any]) -> dict[str, Any]:
    """Append one bounded, redacted agent event with a verifiable hash-chain link."""
    root = repo.resolve()
    if not root.is_dir():
        raise SessionLedgerError("repository root does not exist")
    path = root / LEDGER
    path.parent.mkdir(parents=True, exist_ok=True)
    records = _read_records(root)
    if len(records) >= MAX_RECORDS:
        raise SessionLedgerError("agent session ledger reached its record limit")
    previous = records[-1]["hash"] if records else "0" * 64
    record = _event_record(event, decision)
    record.update({"sequence": len(records) + 1, "previous_hash": previous})
    digest = hashlib.sha256((previous + _canonical(record).decode("utf-8")).encode("utf-8")).hexdigest()
    record["hash"] = digest
    payload = (_canonical(record).decode("utf-8") + "\n").encode("utf-8")
    if path.exists() and path.stat().st_size + len(payload) > MAX_BYTES:
        raise SessionLedgerError("agent session ledger would exceed 32 MiB")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        if os.write(fd, payload) != len(payload):
            raise OSError("short write to agent session ledger")
    finally:
        os.close(fd)
    return {"sequence": record["sequence"], "event_id": record["event_id"], "hash": digest, "path": LEDGER}


def session_report(repo: Path, limit: int = 100, session_id: str = "") -> dict[str, Any]:
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 1000:
        raise SessionLedgerError("limit must be between 1 and 1000")
    records = _read_records(repo.resolve())
    if session_id:
        records = [item for item in records if item.get("session_id") == session_id]
    selected = records[-limit:]
    decisions: dict[str, int] = {}
    tools: dict[str, int] = {}
    sessions: dict[str, dict[str, Any]] = {}
    for item in records:
        decision = str(item.get("decision", "unknown"))
        decisions[decision] = decisions.get(decision, 0) + 1
        tool = str(item.get("tool_name", "unknown"))
        tools[tool] = tools.get(tool, 0) + 1
        sid = str(item.get("session_id", "default"))
        group = sessions.setdefault(sid, {"session_id": sid, "events": 0, "blocked": 0, "last_seen": item.get("at", "")})
        group["events"] += 1
        group["last_seen"] = item.get("at", "")
        if decision == "block":
            group["blocked"] += 1
    return {
        "ledger": LEDGER,
        "integrity": "valid",
        "total_events": len(records),
        "returned_events": len(selected),
        "decisions": decisions,
        "tools": tools,
        "sessions": sorted(sessions.values(), key=lambda item: item["last_seen"], reverse=True)[:100],
        "events": list(reversed(selected)),
    }


def verify_session_ledger(repo: Path) -> dict[str, Any]:
    records = _read_records(repo.resolve())
    return {"valid": True, "ledger": LEDGER, "events_verified": len(records),
            "head_hash": records[-1]["hash"] if records else "0" * 64}
