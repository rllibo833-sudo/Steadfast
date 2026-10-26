from __future__ import annotations

import fnmatch
import hashlib
import hmac
import json
import os
import re
import subprocess
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from .checks import scope_findings
from .goals import goal_report
from .impact import analyze_change_impact
from .inventory import inventory_report
from .pipeline import run_pipeline
from .history import record_run
from .policy import load_policy
from .workcycle import _without_goal_status, find_goal

ORDER_DIR = ".steadfast/work-orders"
MAX_ORDER_BYTES = 1_000_000
MAX_ORDER_FILES = 10_000
VOLATILE_PATHS = {
    ".steadfast/work-cycle.json", ".steadfast/work-cycle.jsonl",
    ".steadfast/runs.jsonl", ".steadfast/automation-runs.jsonl",
    ".steadfast/finding-ledger.json", ".steadfast/finding-events.jsonl",
    ".steadfast/agent-sessions.jsonl",
}
ORDER_ID = re.compile(r"^[0-9a-f]{12}$")


class WorkOrderError(ValueError):
    """Raised for invalid or unsafe agent work orders."""


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _stamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _seal(order: dict[str, Any]) -> dict[str, Any]:
    result = dict(order)
    result.pop("integrity_sha256", None)
    result["integrity_sha256"] = hashlib.sha256(_canonical(result)).hexdigest()
    return result


def _verify_seal(order: dict[str, Any]) -> None:
    expected = order.get("integrity_sha256")
    unsigned = dict(order)
    unsigned.pop("integrity_sha256", None)
    actual = hashlib.sha256(_canonical(unsigned)).hexdigest()
    if not isinstance(expected, str) or not hmac.compare_digest(expected, actual):
        raise WorkOrderError("work order integrity check failed; do not trust this contract")


def _order_path(repo: Path, order_id: str) -> Path:
    if not isinstance(order_id, str) or not ORDER_ID.fullmatch(order_id):
        raise WorkOrderError("work order ID must be 12 lowercase hexadecimal characters")
    directory = repo / ORDER_DIR
    if directory.is_symlink():
        raise WorkOrderError("work-order directory may not be a symlink")
    path = directory / f"{order_id}.json"
    if path.is_symlink():
        raise WorkOrderError("work-order file may not be a symlink")
    return path


def _read_order(repo: Path, order_id: str) -> dict[str, Any]:
    path = _order_path(repo.resolve(), order_id)
    if not path.is_file():
        raise WorkOrderError(f"work order {order_id!r} not found")
    if path.stat().st_size > MAX_ORDER_BYTES:
        raise WorkOrderError("work order exceeds 1 MB")
    try:
        order = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise WorkOrderError(f"work order cannot be read: {exc}") from exc
    if not isinstance(order, dict) or order.get("schema_version") != 1 or order.get("id") != order_id:
        raise WorkOrderError("invalid work-order schema or identity")
    _verify_seal(order)
    return order


def _write_order(repo: Path, order: dict[str, Any], *, create_only: bool = False) -> dict[str, Any]:
    directory = repo / ORDER_DIR
    directory.mkdir(parents=True, exist_ok=True)
    if directory.is_symlink():
        raise WorkOrderError("work-order directory may not be a symlink")
    path = _order_path(repo, str(order.get("id", "")))
    sealed = _seal(order)
    data = json.dumps(sealed, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"
    if len(data) > MAX_ORDER_BYTES:
        raise WorkOrderError("work order exceeds 1 MB")
    if create_only and path.exists():
        raise WorkOrderError("work order already exists")
    temporary = directory / ("." + path.name + "." + uuid.uuid4().hex + ".tmp")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        if os.write(fd, data) != len(data):
            raise OSError("short write while saving work order")
    finally:
        os.close(fd)
    try:
        if create_only and path.exists():
            raise WorkOrderError("work order already exists")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    return sealed


def _head(repo: Path) -> str:
    try:
        result = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                                capture_output=True, text=True, timeout=5, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def _path_matches(path: str, pattern: str) -> bool:
    return fnmatch.fnmatchcase(path, pattern) or (
        pattern.endswith("/**") and path.startswith(pattern[:-2])
    )


def _safe_pattern(pattern: str) -> str:
    if not isinstance(pattern, str) or not pattern.strip():
        raise WorkOrderError("scope patterns must be non-empty strings")
    value = pattern.strip().replace("\\", "/")
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or value.startswith("/"):
        raise WorkOrderError(f"unsafe work-order scope pattern: {pattern!r}")
    if any(ch in value for ch in ("?", "[", "]", "{", "}", "\x00")):
        raise WorkOrderError(f"unsupported wildcard in scope pattern: {pattern!r}")
    if "*" in value and not value.endswith("/**") and value != "**":
        raise WorkOrderError("scope wildcards are limited to a terminal /** pattern")
    return value


def _scope_is_allowed(pattern: str, allowed: list[str]) -> bool:
    if pattern in allowed:
        return True
    if pattern.endswith("/**"):
        prefix = pattern[:-2]
        for permitted in allowed:
            if permitted.endswith("/**") and prefix.startswith(permitted[:-2]):
                return True
        return False
    return any(_path_matches(pattern, permitted) for permitted in allowed)


def _select_scope(policy: dict[str, Any], scope_paths: Iterable[str] | None) -> list[str]:
    allowed = [str(item) for item in policy.get("allowed_paths", [])]
    if scope_paths is None:
        return allowed
    selected = sorted(set(_safe_pattern(item) for item in scope_paths))
    if not selected:
        raise WorkOrderError("explicit scope must include at least one path or directory pattern")
    for pattern in selected:
        if not _scope_is_allowed(pattern, allowed):
            raise WorkOrderError(f"scope {pattern!r} would expand beyond policy allowed_paths")
    return selected


def _snapshot(repo: Path) -> list[dict[str, Any]]:
    inventory = inventory_report(repo)
    rows = []
    for item in inventory.get("files", []):
        path = str(item.get("path", ""))
        if not path or path in VOLATILE_PATHS or path.startswith(ORDER_DIR + "/") or path.startswith(".steadfast/artifacts/"):
            continue
        digest = item.get("sha256")
        if path.startswith(".steadfast/goals/") and path.endswith(".md"):
            target = repo / path
            if target.is_file() and not target.is_symlink():
                digest = hashlib.sha256(_without_goal_status(target.read_bytes())).hexdigest()
        rows.append({"path": path, "sha256": digest, "bytes": int(item.get("bytes", 0))})
        if len(rows) > MAX_ORDER_FILES:
            raise WorkOrderError(f"work-order snapshot is limited to {MAX_ORDER_FILES} files")
    return rows


def _goal_hash(repo: Path, relative: str) -> str:
    path = repo / relative
    if not path.is_file() or path.is_symlink():
        return ""
    raw = path.read_bytes()
    if relative.startswith(".steadfast/goals/") and relative.endswith(".md"):
        raw = _without_goal_status(raw)
    return hashlib.sha256(raw).hexdigest()


def _policy_hash(policy: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical(policy)).hexdigest()


def _goal_details(repo: Path, goal_id: str) -> tuple[str, list[str], list[str]]:
    goal_path, criteria = find_goal(repo, goal_id)
    if goal_path == ".steadfast/goal.md":
        return goal_path, criteria, []
    report = goal_report(repo, load_policy(repo))
    item = next((goal for goal in report.get("goals", []) if goal.get("id") == goal_id), None)
    if item is None:
        raise WorkOrderError(f"goal {goal_id!r} is not part of the configured goal graph")
    if item.get("status") not in {"ready", "active"}:
        raise WorkOrderError(f"goal {goal_id!r} must be ready or active, not {item.get('status')!r}")
    by_id = {str(goal.get("id")): goal for goal in report.get("goals", [])}
    waiting = [str(dep) for dep in item.get("depends_on", [])
               if dep not in by_id or by_id[dep].get("status") != "done"]
    if waiting:
        raise WorkOrderError(f"goal {goal_id!r} has unfinished dependencies: " + ", ".join(waiting))
    return goal_path, criteria, list(item.get("depends_on", []))


def list_work_orders(repo: Path, limit: int = 100) -> dict[str, Any]:
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 1000:
        raise WorkOrderError("limit must be between 1 and 1000")
    directory = repo.resolve() / ORDER_DIR
    if not directory.exists():
        return {"count": 0, "work_orders": [], "directory": ORDER_DIR}
    if directory.is_symlink():
        raise WorkOrderError("work-order directory may not be a symlink")
    files = sorted(directory.glob("*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    orders = []
    for path in files[:limit]:
        if path.is_symlink() or not path.is_file():
            continue
        order = _read_order(repo.resolve(), path.stem)
        status = order.get("status", "invalid")
        if status in {"issued", "in_progress"} and _now() > datetime.fromisoformat(order["expires_at"]):
            status = "expired"
        orders.append({"id": order["id"], "goal_id": order["goal_id"], "title": order["title"],
                       "owner": order["owner"], "status": status, "created_at": order["created_at"],
                       "expires_at": order["expires_at"], "scope_count": len(order["scope_paths"])})
    return {"count": len(orders), "work_orders": orders, "directory": ORDER_DIR}


def issue_work_order(
    repo: Path,
    goal_id: str,
    *,
    owner: str = "",
    ttl_minutes: int = 240,
    scope_paths: Iterable[str] | None = None,
) -> dict[str, Any]:
    root = repo.resolve()
    if not root.is_dir():
        raise WorkOrderError("repository root does not exist")
    if isinstance(ttl_minutes, bool) or not isinstance(ttl_minutes, int) or not 5 <= ttl_minutes <= 10_080:
        raise WorkOrderError("TTL must be between 5 minutes and 7 days")
    if not isinstance(owner, str) or len(owner) > 120:
        raise WorkOrderError("owner must be text of at most 120 characters")
    existing = list_work_orders(root, limit=1000)["work_orders"]
    active = [item["id"] for item in existing if item["status"] in {"issued", "in_progress"}]
    if active:
        raise WorkOrderError("an active work order already exists: " + active[0])
    policy = load_policy(root)
    goal_path, acceptance, dependencies = _goal_details(root, goal_id)
    scope = _select_scope(policy, scope_paths)
    baseline = _snapshot(root)
    if len(_canonical(baseline)) > 4 * 1024 * 1024:
        raise WorkOrderError("work-order baseline snapshot exceeds 4 MiB")
    created = _now()
    order = {
        "schema_version": 1,
        "id": uuid.uuid4().hex[:12],
        "goal_id": goal_id,
        "title": goal_id,
        "owner": owner.strip(),
        "status": "issued",
        "created_at": _stamp(created),
        "expires_at": _stamp(created + timedelta(minutes=ttl_minutes)),
        "goal_path": goal_path,
        "goal_sha256": _goal_hash(root, goal_path),
        "dependencies": dependencies,
        "acceptance": [{"id": f"AC-{i:02d}", "criterion": value}
                       for i, value in enumerate(acceptance, 1)],
        "scope_paths": scope,
        "policy_sha256": _policy_hash(policy),
        "base_commit": _head(root),
        "baseline_files": baseline,
        "required_gates": ["unit-tests", "scope-check", "security-check", "docs-check"],
        "verification": None,
        "limitations": [
            "SHA-256 provides integrity checking, not a digital signature or producer authentication.",
            "Path scopes and source/test links are heuristic; reviewers remain responsible for semantic correctness.",
        ],
    }
    return _write_order(root, order, create_only=True)


def show_work_order(repo: Path, order_id: str) -> dict[str, Any]:
    return _read_order(repo.resolve(), order_id)


def active_work_order(repo: Path) -> dict[str, Any] | None:
    orders = list_work_orders(repo, limit=1000)["work_orders"]
    active = [item for item in orders if item["status"] in {"issued", "in_progress"}]
    if not active:
        return None
    return _read_order(repo.resolve(), active[0]["id"])


def matches_work_order_scope(path: str, scope_paths: list[str]) -> bool:
    normalized = path.replace("\\", "/")
    return any(_path_matches(normalized, pattern) for pattern in scope_paths)


def verify_work_order(repo: Path, order_id: str) -> dict[str, Any]:
    root = repo.resolve()
    order = _read_order(root, order_id)
    if order.get("status") not in {"issued", "in_progress"}:
        raise WorkOrderError(f"work order cannot be verified from status {order.get('status')!r}")
    if _now() > datetime.fromisoformat(order["expires_at"]):
        order["status"] = "expired"
        _write_order(root, order)
        raise WorkOrderError("work order has expired")
    policy = load_policy(root)
    policy_unchanged = _policy_hash(policy) == order.get("policy_sha256")
    goal_unchanged = _goal_hash(root, str(order.get("goal_path", ""))) == order.get("goal_sha256")
    current = {item["path"]: item for item in _snapshot(root)}
    baseline = {item["path"]: item for item in order.get("baseline_files", [])}
    changed = sorted(path for path in set(current) | set(baseline)
                     if current.get(path, {}).get("sha256") != baseline.get(path, {}).get("sha256"))
    if any(path.startswith(ORDER_DIR + "/") or path in VOLATILE_PATHS or path.startswith(".steadfast/artifacts/") for path in changed):
        changed = [path for path in changed if not (
            path.startswith(ORDER_DIR + "/") or path in VOLATILE_PATHS or path.startswith(".steadfast/artifacts/")
        )]
    scope = [item for item in scope_findings(root, policy, changed)]
    if not changed:
        scope.append({
            "severity": "error",
            "code": "WORK_ORDER_NO_CHANGES",
            "path": "",
            "message": "No repository changes were produced for this work order; an unchanged workspace cannot be accepted as completed work.",
        })
    if not goal_unchanged:
        scope.append({"severity": "error", "code": "WORK_ORDER_GOAL_CHANGED",
                      "path": str(order.get("goal_path", "")),
                      "message": "Goal acceptance criteria or metadata changed after the work order was issued."})
    outside_order_scope = [path for path in changed if not matches_work_order_scope(path, order["scope_paths"])]
    for path in outside_order_scope:
        scope.append({"severity": "error", "code": "WORK_ORDER_SCOPE_ESCAPE", "path": path,
                      "message": "Changed file is outside the issued work-order scope."})
    impact = analyze_change_impact(root, paths=changed)
    pipeline = run_pipeline(root)
    try:
        run = record_run(root, ".steadfast/runs.jsonl", pipeline)
        pipeline["history_record"] = run["run_id"]
    except (OSError, ValueError) as exc:
        pipeline["history_error"] = str(exc)
        pipeline["passed"] = False
    scope_passed = not any(item.get("severity") == "error" for item in scope)
    passed = bool(pipeline.get("passed")) and scope_passed and bool(impact.get("passed")) and policy_unchanged and goal_unchanged
    result = {
        "passed": passed,
        "verified_at": _stamp(_now()),
        "base_commit": order.get("base_commit", ""),
        "current_commit": _head(root),
        "policy_unchanged": policy_unchanged,
        "goal_unchanged": goal_unchanged,
        "changed_paths": changed,
        "scope": {"passed": scope_passed, "findings": scope},
        "impact": impact,
        "pipeline": pipeline,
    }
    order["verification"] = result
    order["status"] = "verified" if passed else "in_progress"
    _write_order(root, order)
    return result



def render_work_order_prompt(repo: Path, order_id: str) -> str:
    """Render a bounded, copy-ready instruction for an external coding agent."""
    order = show_work_order(repo, order_id)
    if order.get("status") not in {"issued", "in_progress"}:
        raise WorkOrderError(f"work order prompt unavailable for status {order.get('status')!r}")
    if _now() > datetime.fromisoformat(order["expires_at"]):
        raise WorkOrderError("work order has expired")
    criteria = "\\n".join(
        f"- [{item.get('id', 'AC')}] {item.get('criterion', '')}"
        for item in order.get("acceptance", [])
    ) or "- Follow the goal's acceptance criteria in the repository."
    scope = "\\n".join(f"- `{path}`" for path in order.get("scope_paths", []))
    return (
        f"# Steadfast work order {order['id']}\\n\\n"
        f"Goal: {order.get('goal_id', '')}\\n"
        f"Owner: {order.get('owner') or 'unassigned'}\\n"
        f"Expires: {order.get('expires_at', '')}\\n\\n"
        "## Required outcome\\n"
        "Implement the goal in the repository. Make real, reviewable source changes; "
        "do not claim completion without changes and verification.\\n\\n"
        "## Acceptance criteria\\n" + criteria + "\\n\\n"
        "## Allowed paths\\n" + scope + "\\n\\n"
        "## Rules\\n"
        "- Read the repository policy and relevant existing code before editing.\\n"
        "- Do not modify files outside the allowed paths.\\n"
        "- Do not weaken tests, policy, or verification to force a pass.\\n"
        "- Add or update tests for behavior changes.\\n"
        "- Run the relevant tests and report exact commands and outcomes.\\n"
        "- Leave changes in the workspace; do not commit, push, or claim verification unless asked.\\n\\n"
        f"## Verification command\\n`steadfast --repo . work-order verify {order['id']}`\\n"
    )

def close_work_order(repo: Path, order_id: str) -> dict[str, Any]:
    root = repo.resolve()
    order = _read_order(root, order_id)
    if order.get("status") != "verified" or not order.get("verification", {}).get("passed"):
        raise WorkOrderError("work order can close only after a passing verification")
    order["status"] = "closed"
    order["closed_at"] = _stamp(_now())
    return _write_order(root, order)
