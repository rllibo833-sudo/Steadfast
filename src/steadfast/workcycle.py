from __future__ import annotations
import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from .pipeline import run_pipeline
from .history import record_run
from .checks import scope_findings
from .gitops import changed_paths
from .policy import load_policy

STATE = ".steadfast/work-cycle.json"
JOURNAL = ".steadfast/work-cycle.jsonl"

def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()

def read_state(repo: Path) -> dict[str, Any]:
    path = repo / STATE
    if not path.exists():
        return {"schema_version": 1, "task": None}
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("schema_version") != 1:
        raise ValueError("invalid work-cycle state")
    return value

def save(repo: Path, state: dict[str, Any], event: str, details: dict[str, Any]) -> None:
    journal = repo / JOURNAL
    journal.parent.mkdir(parents=True, exist_ok=True)
    prior = journal.read_text(encoding="utf-8").splitlines() if journal.exists() else []
    previous = prior[-1] if prior else ""
    record = {"id": uuid.uuid4().hex, "at": now(), "event": event,
              "task_id": state["task"]["id"], "details": details,
              "previous_record_sha256": hashlib.sha256(previous.encode()).hexdigest() if previous else ""}
    line = json.dumps(record, ensure_ascii=False, separators=(",", ":"))
    with journal.open("a", encoding="utf-8") as stream:
        stream.write(line + "\n")
    target = repo / STATE
    temporary = target.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(target)

def find_goal(repo: Path, goal_id: str) -> tuple[str, list[str]]:
    paths = [repo / ".steadfast" / "goal.md"] + sorted((repo / ".steadfast" / "goals").glob("*.md"))
    for path in paths:
        if not path.is_file():
            continue
        if path.name != "goal.md" and path.stem != goal_id:
            continue
        if path.name == "goal.md" and goal_id not in {"goal", "product"}:
            continue
        lines, active = [], False
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("## "):
                active = line[3:].strip().lower() == "acceptance criteria"
            elif active and line.strip().startswith(("- [ ]", "- [x]", "- [X]")):
                item = line.strip().split("]", 1)[-1].strip()
                if item:
                    lines.append(item)
        if not lines:
            raise ValueError(f"goal {goal_id!r} has no acceptance checklist")
        return path.relative_to(repo).as_posix(), lines
    raise ValueError(f"goal {goal_id!r} not found")

def start_cycle(repo: Path, goal_id: str, title: str = "") -> dict[str, Any]:
    repo = repo.resolve()
    old = read_state(repo).get("task")
    if old and old["status"] not in {"completed", "blocked"}:
        raise ValueError("an active task already exists")
    path, criteria = find_goal(repo, goal_id)
    task = {"id": uuid.uuid4().hex[:12], "goal_id": goal_id, "title": title or goal_id,
            "goal_path": path, "status": "in_progress", "started_at": now(),
            "acceptance": [{"id": f"AC-{i:02d}", "criterion": item, "evidence": None}
                           for i, item in enumerate(criteria, 1)], "verification": None}
    state = {"schema_version": 1, "task": task}
    save(repo, state, "task_started", {"goal_id": goal_id})
    return task

def attach_evidence(repo: Path, criterion_id: str, relative: str, note: str = "") -> dict[str, Any]:
    repo = repo.resolve()
    state = read_state(repo)
    task = state.get("task")
    if not task or task["status"] not in {"in_progress", "verifying"}:
        raise ValueError("no active task")
    item = next((x for x in task["acceptance"] if x["id"] == criterion_id), None)
    if item is None:
        raise ValueError(f"unknown criterion {criterion_id}")
    candidate = Path(relative)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ValueError("evidence path must be repository-relative")
    path = (repo / candidate).resolve(strict=True)
    if not path.is_file() or path.is_symlink():
        raise ValueError("evidence must be a regular file")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    item["evidence"] = {"path": path.relative_to(repo).as_posix(), "sha256": digest, "note": note, "attached_at": now()}
    save(repo, state, "evidence_attached", {"criterion_id": criterion_id, "path": item["evidence"]["path"]})
    return task

def verify_cycle(repo: Path) -> dict[str, Any]:
    repo = repo.resolve()
    state = read_state(repo)
    task = state.get("task")
    if not task or task["status"] not in {"in_progress", "verifying"}:
        raise ValueError("start a task before verifying")
    task["status"] = "verifying"
    result = run_pipeline(repo)
    record = record_run(repo, ".steadfast/runs.jsonl", result)
    result["history_record"] = record["run_id"]
    paths = changed_paths(repo)
    findings = scope_findings(repo, load_policy(repo), paths)
    result["scope"] = {"passed": not any(x.get("severity") == "error" for x in findings),
                       "changed_paths": paths, "findings": findings}
    result["passed"] = bool(result["passed"]) and result["scope"]["passed"]
    result["verified_at"] = now()
    task["verification"] = result
    task["status"] = "verifying" if result["passed"] else "in_progress"
    save(repo, state, "verification_finished", {"passed": result["passed"]})
    return result

def complete_cycle(repo: Path) -> dict[str, Any]:
    repo = repo.resolve()
    state = read_state(repo)
    task = state.get("task")
    if not task or task["status"] not in {"in_progress", "verifying"}:
        raise ValueError("no active task")
    if not task.get("verification") or not task["verification"].get("passed"):
        raise ValueError("completion blocked: run a passing pipeline and scope check first")
    missing = []
    for item in task["acceptance"]:
        proof = item.get("evidence")
        if not proof:
            missing.append(item["id"])
            continue
        try:
            path = (repo / proof["path"]).resolve(strict=True)
            path.relative_to(repo)
            if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != proof["sha256"]:
                missing.append(item["id"])
        except (OSError, ValueError, KeyError):
            missing.append(item["id"])
    if missing:
        raise ValueError("completion blocked: missing/changed evidence: " + ", ".join(missing))
    task["status"], task["completed_at"] = "completed", now()
    save(repo, state, "task_completed", {"criteria_count": len(task["acceptance"])})
    return task

def block_cycle(repo: Path, reason: str) -> dict[str, Any]:
    if not reason.strip():
        raise ValueError("block reason is required")
    state = read_state(repo.resolve())
    task = state.get("task")
    if not task or task["status"] in {"completed", "blocked"}:
        raise ValueError("no active task")
    task["status"], task["block_reason"] = "blocked", reason.strip()
    save(repo.resolve(), state, "task_blocked", {"reason": task["block_reason"]})
    return task

def cycle_status(repo: Path) -> dict[str, Any]:
    task = read_state(repo.resolve()).get("task")
    if task:
        task = dict(task)
        task["acceptance_summary"] = {"total": len(task["acceptance"]),
            "with_evidence": sum(bool(x.get("evidence")) for x in task["acceptance"]),
            "missing_evidence": [x["id"] for x in task["acceptance"] if not x.get("evidence")]}
    return {"state_file": STATE, "journal_file": JOURNAL, "task": task}

def cycle_history(repo: Path, limit: int = 20) -> dict[str, Any]:
    if not 1 <= limit <= 1000:
        raise ValueError("limit must be from 1 to 1000")
    path = repo.resolve() / JOURNAL
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()] if path.exists() else []
    return {"count": min(limit, len(records)), "events": list(reversed(records[-limit:])), "journal": JOURNAL}
