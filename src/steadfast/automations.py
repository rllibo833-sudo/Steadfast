from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .checks import evidence_findings, run_audit
from .findings import finding_metrics, scan_findings
from .goals import goal_report
from .inventory import inventory_report
from .planner import execution_plan
from .policy import load_policy
from .release import release_report
from .security import security_findings, workflow_findings

MANIFEST = ".steadfast/automations.json"
HISTORY = ".steadfast/automation-runs.jsonl"
MAX_HISTORY_BYTES = 16 * 1024 * 1024
MAX_STEPS = 12

# The registry is deliberately closed: workflow files select named built-ins,
# never arbitrary Python imports, shell commands, URLs, or dynamic expressions.
ACTIONS: dict[str, tuple[str, Callable[[Path], dict[str, Any]]]] = {
    "audit": ("Check policy, evidence, contracts and repository scope.", lambda repo: run_audit(repo)),
    "security": ("Scan source and CI workflows for common security hazards.", lambda repo: {
        "findings": security_findings(repo, load_policy(repo)) + workflow_findings(repo)}),
    "evidence": ("Check configured verification evidence files.", lambda repo: {
        "findings": evidence_findings(repo, load_policy(repo))}),
    "release": ("Evaluate release readiness without publishing.", lambda repo: release_report(repo)),
    "inventory": ("Inventory implementation files and content digests.", lambda repo: inventory_report(repo)),
    "plan": ("Build a dependency-aware task execution plan.", lambda repo: execution_plan(repo)),
    "goals": ("Validate and report configured goals.", lambda repo: goal_report(repo, load_policy(repo))),
    "finding-metrics": ("Summarize the current finding ledger.", lambda repo: finding_metrics(repo)),
    "findings-scan": ("Refresh the finding ledger from live repository checks.", lambda repo: scan_findings(repo)),
}

DEFAULT_WORKFLOWS = [
    {"id": "quick-health", "name": "Quick project health", "description": "Audit the repository, scan security risks and inspect required evidence.", "steps": ["audit", "security", "evidence"]},
    {"id": "release-review", "name": "Release review", "description": "Check release readiness, source security and implementation inventory.", "steps": ["release", "security", "inventory"]},
    {"id": "work-queue", "name": "Next work queue", "description": "Refresh open findings, calculate risk metrics and plan the next dependency-ready goal.", "steps": ["findings-scan", "finding-metrics", "plan"]},
]


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _safe_repo_file(repo: Path, relative: str) -> Path:
    candidate = Path(relative)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ValueError("workflow manifest must be repository-relative")
    root = repo.resolve()
    lexical = root / candidate
    current = root
    for part in candidate.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError("workflow manifest path cannot traverse symlinks")
    resolved = lexical.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError("workflow manifest resolves outside repository") from exc
    return resolved


def _validate_workflows(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value:
        raise ValueError("automation manifest must contain a non-empty workflows array")
    if len(value) > 50:
        raise ValueError("automation manifest is limited to 50 workflows")
    seen: set[str] = set()
    result = []
    for index, raw in enumerate(value):
        if not isinstance(raw, dict):
            raise ValueError(f"workflow[{index}] must be an object")
        workflow_id = raw.get("id")
        name = raw.get("name")
        description = raw.get("description", "")
        steps = raw.get("steps")
        if not isinstance(workflow_id, str) or not workflow_id or not workflow_id.replace("-", "").replace("_", "").isalnum():
            raise ValueError(f"workflow[{index}] has an invalid id")
        if workflow_id in seen:
            raise ValueError(f"duplicate workflow id: {workflow_id}")
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"workflow {workflow_id} needs a name")
        if not isinstance(description, str):
            raise ValueError(f"workflow {workflow_id} description must be text")
        if not isinstance(steps, list) or not steps or len(steps) > MAX_STEPS:
            raise ValueError(f"workflow {workflow_id} needs 1-{MAX_STEPS} steps")
        for action in steps:
            if not isinstance(action, str) or action not in ACTIONS:
                raise ValueError(f"workflow {workflow_id} uses unsupported action {action!r}; allowed: {', '.join(ACTIONS)}")
        seen.add(workflow_id)
        result.append({"id": workflow_id, "name": name.strip(), "description": description.strip(), "steps": list(steps)})
    return result


def list_automations(repo: Path, manifest: str = MANIFEST) -> dict[str, Any]:
    root = repo.resolve()
    path = _safe_repo_file(root, manifest)
    if not path.exists():
        workflows = DEFAULT_WORKFLOWS
        source = "built-in"
    else:
        if path.stat().st_size > 256_000:
            raise ValueError("automation manifest exceeds 256 KB")
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict) or value.get("schema_version") != 1:
            raise ValueError("unsupported automation manifest schema")
        workflows = _validate_workflows(value.get("workflows"))
        source = manifest
    return {"schema_version": 1, "source": source,
            "available_actions": [{"id": key, "description": item[0]} for key, item in ACTIONS.items()],
            "workflows": [dict(item, step_count=len(item["steps"])) for item in workflows]}


def _append_history(repo: Path, record: dict[str, Any]) -> None:
    path = _safe_repo_file(repo, HISTORY)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and (path.is_symlink() or path.stat().st_size > MAX_HISTORY_BYTES):
        raise ValueError("automation history is unsafe or exceeds 16 MiB")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        data = (json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n").encode()
        if os.write(fd, data) != len(data):
            raise OSError("short write to automation history")
    finally:
        os.close(fd)


def run_automation(repo: Path, workflow_id: str, manifest: str = MANIFEST) -> dict[str, Any]:
    root = repo.resolve()
    config = list_automations(root, manifest)
    workflow = next((item for item in config["workflows"] if item["id"] == workflow_id), None)
    if workflow is None:
        raise ValueError(f"unknown automation {workflow_id!r}")
    started = _now()
    run_id = uuid.uuid4().hex[:16]
    results = []
    overall = True
    for index, action_id in enumerate(workflow["steps"], 1):
        label, action = ACTIONS[action_id]
        step_started = _now()
        try:
            result = action(root)
            failed = result.get("passed") is False or result.get("ready") is False
            findings = result.get("findings", [])
            if isinstance(findings, list) and any(isinstance(item, dict) and item.get("severity") == "error" for item in findings):
                failed = True
            step = {"index": index, "action": action_id, "description": label,
                    "status": "failed" if failed else "passed", "started_at": step_started,
                    "finished_at": _now(), "result": result}
        except Exception as exc:
            failed = True
            step = {"index": index, "action": action_id, "description": label,
                    "status": "error", "started_at": step_started, "finished_at": _now(),
                    "error": f"{type(exc).__name__}: {exc}"}
        results.append(step)
        if failed:
            overall = False
            # Each action is observational or writes only the explicit finding ledger.
            # Stop here so later actions cannot obscure an earlier failure.
            break
    record = {"schema_version": 1, "run_id": run_id, "workflow_id": workflow_id,
              "workflow_name": workflow["name"], "status": "passed" if overall else "failed",
              "started_at": started, "finished_at": _now(), "step_count": len(results),
              "steps": results}
    _append_history(root, record)
    return record


def automation_history(repo: Path, limit: int = 20) -> dict[str, Any]:
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 1000:
        raise ValueError("history limit must be between 1 and 1000")
    path = _safe_repo_file(repo.resolve(), HISTORY)
    if not path.exists():
        return {"count": 0, "runs": [], "history": HISTORY}
    if path.stat().st_size > MAX_HISTORY_BYTES:
        raise ValueError("automation history exceeds 16 MiB")
    records = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        try:
            item = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"automation history is corrupt at line {number}") from exc
        if not isinstance(item, dict) or item.get("schema_version") != 1:
            raise ValueError(f"automation history has invalid record at line {number}")
        records.append(item)
    recent = list(reversed(records[-limit:]))
    return {"count": len(recent), "runs": recent, "history": HISTORY}
