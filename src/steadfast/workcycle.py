from __future__ import annotations
import hashlib
import json
import os
import re
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

_VOLATILE_FILES = {
    ".steadfast/work-cycle.json",
    ".steadfast/work-cycle.jsonl",
    ".steadfast/runs.jsonl",
    ".steadfast/automation-runs.jsonl",
    ".steadfast/finding-ledger.json",
    ".steadfast/finding-events.jsonl",
}
_IGNORED_DIRS = {".git", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".venv", "venv", "node_modules"}

def _workspace_fingerprint(repo: Path) -> str:
    """Hash the workspace contents while excluding Steadfast's own runtime journals."""
    root = repo.resolve()
    digest = hashlib.sha256()
    total_bytes = 0
    file_count = 0
    for current, dirs, names in os.walk(root, topdown=True, followlinks=False):
        base = Path(current)
        dirs[:] = sorted(
            name for name in dirs
            if name not in _IGNORED_DIRS and not (base / name).is_symlink()
        )
        for name in sorted(names):
            path = base / name
            relative = path.relative_to(root).as_posix()
            if relative in _VOLATILE_FILES:
                continue
            file_count += 1
            if file_count > 100_000:
                raise ValueError("workspace verification limit exceeded: more than 100,000 files")
            if path.is_symlink():
                payload = ("symlink:" + os.readlink(path)).encode("utf-8", errors="surrogateescape")
            elif path.is_file():
                size = path.stat().st_size
                total_bytes += size
                if total_bytes > 128 * 1024 * 1024:
                    raise ValueError("workspace verification limit exceeded: more than 128 MiB")
                file_hash = hashlib.sha256()
                normalized_size = size
                # Goal status is a lifecycle marker updated by this engine after
                # verified completion; normalize only that metadata field so the
                # bookkeeping transition does not invalidate its own proof.
                if relative.startswith(".steadfast/goals/") and path.suffix.lower() == ".md":
                    raw = path.read_bytes()
                    normalized = _without_goal_status(raw)
                    normalized_size = len(normalized)
                    file_hash.update(normalized)
                else:
                    with path.open("rb") as stream:
                        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                            file_hash.update(chunk)
                payload = b"file:" + str(normalized_size).encode("ascii") + b":" + file_hash.digest()
            else:
                continue
            digest.update(relative.encode("utf-8", errors="surrogateescape"))
            digest.update(b"\\0")
            digest.update(payload)
            digest.update(b"\\n")
    return digest.hexdigest()

def read_state(repo: Path) -> dict[str, Any]:
    path = repo / STATE
    if not path.exists():
        return {"schema_version": 1, "task": None}
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("schema_version") != 1:
        raise ValueError("invalid work-cycle state")
    return value

def _validated_journal(repo: Path) -> list[dict[str, Any]]:
    journal = repo / JOURNAL
    if not journal.exists():
        return []
    if journal.is_symlink() or journal.stat().st_size > 16 * 1024 * 1024:
        raise ValueError("work-cycle journal is unsafe or exceeds 16 MiB")
    records: list[dict[str, Any]] = []
    previous = "0" * 64
    try:
        lines = journal.read_text(encoding="utf-8").splitlines()
        for number, line in enumerate(lines, 1):
            record = json.loads(line)
            if not isinstance(record, dict):
                raise ValueError(f"invalid journal record at line {number}")
            digest = record.pop("hash", None)
            if record.get("previous_hash") != previous:
                raise ValueError(f"work-cycle journal chain invalid at line {number}")
            canonical = json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
            expected = hashlib.sha256((previous + canonical).encode("utf-8")).hexdigest()
            if digest != expected:
                raise ValueError(f"work-cycle journal integrity check failed at line {number}")
            record["hash"] = digest
            records.append(record)
            previous = digest
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read work-cycle journal: {exc}") from exc
    return records

def save(repo: Path, state: dict[str, Any], event: str, details: dict[str, Any]) -> None:
    journal = repo / JOURNAL
    journal.parent.mkdir(parents=True, exist_ok=True)
    records = _validated_journal(repo)
    previous = records[-1]["hash"] if records else "0" * 64
    record = {"id": uuid.uuid4().hex, "at": now(), "event": event,
              "task_id": state["task"]["id"], "details": details,
              "sequence": len(records) + 1, "previous_hash": previous}
    canonical = json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    record["hash"] = hashlib.sha256((previous + canonical).encode("utf-8")).hexdigest()
    line = json.dumps(record, ensure_ascii=False, separators=(",", ":"))
    with journal.open("a", encoding="utf-8") as stream:
        stream.write(line + "\n")
    target = repo / STATE
    temporary = target.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(target)

def _frontmatter_bounds(text: str) -> tuple[int, int] | None:
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return None
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            return 1, index
    return None


def _goal_metadata(path: Path) -> tuple[str, str]:
    text = path.read_text(encoding="utf-8")
    bounds = _frontmatter_bounds(text)
    goal_id, status = path.stem, "proposed"
    if bounds:
        lines = text.splitlines()
        for line in lines[bounds[0]:bounds[1]]:
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            value = value.strip().strip('"').strip("'")
            if key.strip() == "id":
                goal_id = value
            elif key.strip() == "status":
                status = value.casefold()
    return goal_id, status


def _without_goal_status(raw: bytes) -> bytes:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw
    bounds = _frontmatter_bounds(text)
    if not bounds:
        return raw
    lines = text.splitlines(keepends=True)
    normalized = False
    for index in range(bounds[0], bounds[1]):
        if lines[index].lstrip().startswith("status:"):
            ending = "\r\n" if lines[index].endswith("\r\n") else "\n" if lines[index].endswith("\n") else ""
            lines[index] = "status: __STEADFAST_STATUS_NORMALIZED__" + ending
            normalized = True
            break
    if not normalized:
        ending = "\r\n" if "\r\n" in text else "\n"
        lines.insert(bounds[1], "status: __STEADFAST_STATUS_NORMALIZED__" + ending)
    return "".join(lines).encode("utf-8")


def _sync_goal_status(repo: Path, goal_id: str, status: str) -> str | None:
    directory = repo / ".steadfast" / "goals"
    matches = []
    if directory.is_dir():
        for path in sorted(directory.glob("*.md")):
            if path.is_symlink() or not path.is_file():
                continue
            actual_id, _ = _goal_metadata(path)
            if actual_id == goal_id:
                matches.append(path)
    if not matches:
        return None
    if len(matches) != 1:
        raise ValueError(f"goal {goal_id!r} has multiple matching goal files")
    path = matches[0]
    text = path.read_text(encoding="utf-8")
    bounds = _frontmatter_bounds(text)
    if bounds:
        lines = text.splitlines(keepends=True)
        found = False
        for index in range(bounds[0], bounds[1]):
            if lines[index].lstrip().startswith("status:"):
                prefix, _, _ = lines[index].partition(":")
                ending = "\r\n" if lines[index].endswith("\r\n") else "\n" if lines[index].endswith("\n") else ""
                lines[index] = prefix + ": " + status + ending
                found = True
                break
        if not found:
            ending = "\r\n" if "\r\n" in text else "\n"
            lines.insert(bounds[1], "status: " + status + ending)
        updated = "".join(lines)
    else:
        # A goal without frontmatter has no explicit lifecycle field to update.
        # Do not inject metadata during completion because that would change the
        # already-verified workspace beyond the status-only normalization rule.
        return None
    temporary = path.with_name(path.name + ".steadfast.tmp")
    temporary.write_text(updated, encoding="utf-8")
    temporary.replace(path)
    return path.relative_to(repo).as_posix()


def find_goal(repo: Path, goal_id: str) -> tuple[str, list[str]]:
    root_goal = repo / ".steadfast" / "goal.md"
    candidates = ([root_goal] if goal_id in {"goal", "product"} else [])
    directory = repo / ".steadfast" / "goals"
    if directory.is_dir():
        for path in sorted(directory.glob("*.md")):
            if not path.is_file() or path.is_symlink():
                continue
            actual_id, status = _goal_metadata(path)
            if actual_id == goal_id and status not in {"done", "cancelled"}:
                candidates.append(path)
    for path in candidates:
        text = path.read_text(encoding="utf-8")
        lines, active = [], False
        for line in text.splitlines():
            if line.startswith("## "):
                active = line[3:].strip().lower() == "acceptance criteria"
            elif active and line.strip().startswith(("- [ ]", "- [x]", "- [X]")):
                item = line.strip().split("]", 1)[-1].strip()
                if item:
                    lines.append(item)
        if not lines:
            raise ValueError(f"goal {goal_id!r} has no acceptance checklist")
        return path.relative_to(repo).as_posix(), lines
    raise ValueError(f"goal {goal_id!r} not found, or already done/cancelled")

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

def _evidence_file(repo: Path, relative: str) -> Path:
    candidate = Path(relative)
    if not isinstance(relative, str) or not relative.strip() or candidate.is_absolute() or ".." in candidate.parts:
        raise ValueError("evidence path must be repository-relative")
    current = repo
    for part in candidate.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError("evidence path may not traverse symlinks")
    path = (repo / candidate).resolve(strict=True)
    try:
        path.relative_to(repo.resolve())
    except ValueError as exc:
        raise ValueError("evidence path resolves outside repository") from exc
    if not path.is_file():
        raise ValueError("evidence must be an existing regular file")
    return path

def attach_evidence(repo: Path, criterion_id: str, relative: str, note: str = "") -> dict[str, Any]:
    repo = repo.resolve()
    state = read_state(repo)
    task = state.get("task")
    if not task or task["status"] not in {"in_progress", "verifying"}:
        raise ValueError("no active task")
    item = next((x for x in task["acceptance"] if x["id"] == criterion_id), None)
    if item is None:
        raise ValueError(f"unknown criterion {criterion_id}")
    path = _evidence_file(repo, relative)
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
    result["workspace_sha256"] = _workspace_fingerprint(repo)
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
    verification = task.get("verification")
    if not verification or not verification.get("passed"):
        raise ValueError("completion blocked: run a passing pipeline and scope check first")
    recorded_workspace = verification.get("workspace_sha256")
    if not recorded_workspace:
        raise ValueError("completion blocked: verification has no workspace fingerprint; rerun verification")
    missing = []
    for item in task["acceptance"]:
        proof = item.get("evidence")
        if not proof:
            missing.append(item["id"])
            continue
        try:
            path = _evidence_file(repo, proof["path"])
            if hashlib.sha256(path.read_bytes()).hexdigest() != proof["sha256"]:
                missing.append(item["id"] + " (evidence changed)")
        except (OSError, ValueError, KeyError):
            missing.append(item["id"])
    if missing:
        raise ValueError("completion blocked: missing/changed evidence: " + ", ".join(missing))
    current_workspace = _workspace_fingerprint(repo)
    if current_workspace != recorded_workspace:
        raise ValueError("completion blocked: workspace changed after verification; rerun the configured pipeline and scope check")
    # Keep the dependency planner consistent with the verified task. Only the
    # goal status field is changed; acceptance criteria and all other content
    # remain part of the workspace fingerprint.
    synced_goal = _sync_goal_status(repo, str(task.get("goal_id", "")), "done")
    task["status"], task["completed_at"] = "completed", now()
    save(repo, state, "task_completed", {"criteria_count": len(task["acceptance"]), "goal_status_file": synced_goal})
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
        verification = task.get("verification")
        if verification and verification.get("workspace_sha256"):
            try:
                task["verification_fresh"] = _workspace_fingerprint(repo.resolve()) == verification["workspace_sha256"]
            except (OSError, ValueError):
                task["verification_fresh"] = False
        else:
            task["verification_fresh"] = False
        task["acceptance_summary"] = {"total": len(task["acceptance"]),
            "with_evidence": sum(bool(x.get("evidence")) for x in task["acceptance"]),
            "missing_evidence": [x["id"] for x in task["acceptance"] if not x.get("evidence")]}
    return {"state_file": STATE, "journal_file": JOURNAL, "task": task}

def cycle_history(repo: Path, limit: int = 20) -> dict[str, Any]:
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 1000:
        raise ValueError("limit must be from 1 to 1000")
    records = _validated_journal(repo.resolve())
    recent = list(reversed(records[-limit:]))
    return {"count": len(recent), "events": recent, "journal": JOURNAL}
