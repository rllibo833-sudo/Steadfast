from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Goal:
    goal_id: str
    title: str
    status: str
    depends_on: tuple[str, ...]
    path: str
    acceptance: tuple[str, ...]


STATUSES = {"proposed", "ready", "active", "blocked", "done", "cancelled"}
ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{1,63}$")


def _frontmatter(text: str) -> tuple[dict[str, str], str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, text
    try:
        end = lines.index("---", 1)
    except ValueError:
        return {}, text
    data: dict[str, str] = {}
    for line in lines[1:end]:
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        data[key.strip()] = value.strip().strip('"').strip("'")
    return data, "\n".join(lines[end + 1:])


def _list_value(value: str) -> tuple[str, ...]:
    if not value.strip() or value.strip() in ("[]", "none", "null"):
        return ()
    normalized = value.strip().strip("[]")
    return tuple(item.strip().strip('"').strip("'") for item in normalized.split(",") if item.strip())


def parse_goal(path: Path, root: Path) -> tuple[Goal | None, list[dict[str, str]]]:
    rel = path.relative_to(root).as_posix()
    findings: list[dict[str, str]] = []
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        return None, [{
            "severity": "error", "code": "GOAL_UNREADABLE",
            "path": rel, "message": f"Goal file cannot be read: {exc}",
        }]
    metadata, body = _frontmatter(text)
    goal_id = metadata.get("id", path.stem)
    title = metadata.get("title", "")
    status = metadata.get("status", "proposed").lower()
    depends = _list_value(metadata.get("depends_on", ""))
    if not ID_PATTERN.fullmatch(goal_id):
        findings.append({
            "severity": "error", "code": "GOAL_ID_INVALID", "path": rel,
            "message": "Goal id must be 2-64 lowercase letters, digits, dots, underscores, or hyphens.",
        })
    if not title:
        title_match = re.search(r"^#\s+(.+)$", body, re.MULTILINE)
        title = title_match.group(1).strip() if title_match else ""
    if not title:
        findings.append({
            "severity": "error", "code": "GOAL_TITLE_MISSING", "path": rel,
            "message": "Goal needs a title in frontmatter or a Markdown heading.",
        })
    if status not in STATUSES:
        findings.append({
            "severity": "error", "code": "GOAL_STATUS_INVALID", "path": rel,
            "message": f"Status must be one of: {', '.join(sorted(STATUSES))}.",
        })
    acceptance_section = re.search(
        r"^##\s+Acceptance criteria\s*$([\s\S]*?)(?=^##\s+|\Z)",
        body, re.MULTILINE | re.IGNORECASE,
    )
    acceptance = tuple(
        line.strip()[2:].strip()
        for line in (acceptance_section.group(1).splitlines() if acceptance_section else [])
        if line.strip().startswith(("- [ ]", "- [x]", "- [X]"))
    )
    if not acceptance:
        findings.append({
            "severity": "warning", "code": "GOAL_ACCEPTANCE_MISSING", "path": rel,
            "message": "Goal should include checklist items under an Acceptance criteria heading.",
        })
    return Goal(goal_id, title, status, depends, rel, acceptance), findings


def _cycle_nodes(graph: dict[str, tuple[str, ...]]) -> set[str]:
    visiting: set[str] = set()
    visited: set[str] = set()
    cycle: set[str] = set()

    def visit(node: str, stack: list[str]) -> None:
        if node in visiting:
            try:
                cycle.update(stack[stack.index(node):])
            except ValueError:
                cycle.add(node)
            return
        if node in visited:
            return
        visiting.add(node)
        stack.append(node)
        for parent in graph.get(node, ()):
            if parent in graph:
                visit(parent, stack)
        stack.pop()
        visiting.remove(node)
        visited.add(node)

    for node in graph:
        visit(node, [])
    return cycle


def goal_report(repo: Path, policy: dict[str, Any]) -> dict[str, Any]:
    directory = repo / ".steadfast" / "goals"
    goals: list[Goal] = []
    findings: list[dict[str, str]] = []
    if not directory.exists():
        return {
            "goals": [], "findings": [{
                "severity": "info", "code": "GOAL_DIRECTORY_NOT_CONFIGURED",
                "path": ".steadfast/goals",
                "message": "No goal graph configured. Add Markdown goal files to enable dependency tracking.",
            }],
            "summary": {"total": 0, "active": 0, "done": 0},
        }
    for path in sorted(directory.glob("*.md")):
        goal, errors = parse_goal(path, repo)
        findings.extend(errors)
        if goal:
            goals.append(goal)
    ids: dict[str, Goal] = {}
    for goal in goals:
        if goal.goal_id in ids:
            findings.append({
                "severity": "error", "code": "GOAL_ID_DUPLICATE", "path": goal.path,
                "message": f"Goal id {goal.goal_id!r} is also used by {ids[goal.goal_id].path}.",
            })
        else:
            ids[goal.goal_id] = goal
    graph = {goal.goal_id: goal.depends_on for goal in goals}
    for goal in goals:
        for dependency in goal.depends_on:
            if dependency not in ids:
                findings.append({
                    "severity": "error", "code": "GOAL_DEPENDENCY_MISSING", "path": goal.path,
                    "message": f"Dependency {dependency!r} does not identify a known goal.",
                })
            elif goal.status == "active" and ids[dependency].status != "done":
                findings.append({
                    "severity": "warning", "code": "GOAL_DEPENDENCY_NOT_DONE", "path": goal.path,
                    "message": f"Active goal depends on {dependency!r}, which is {ids[dependency].status}.",
                })
    for goal_id in sorted(_cycle_nodes(graph)):
        findings.append({
            "severity": "error", "code": "GOAL_DEPENDENCY_CYCLE",
            "path": ids[goal_id].path,
            "message": f"Goal {goal_id!r} participates in a dependency cycle.",
        })
    active = [goal for goal in goals if goal.status == "active"]
    limit = policy.get("max_active_goals", 3)
    if len(active) > limit:
        findings.append({
            "severity": "error", "code": "ACTIVE_GOAL_LIMIT_EXCEEDED",
            "path": ".steadfast/goals",
            "message": f"{len(active)} active goals exceed configured limit {limit}.",
        })
    return {
        "goals": [{
            "id": goal.goal_id, "title": goal.title, "status": goal.status,
            "depends_on": list(goal.depends_on), "path": goal.path,
            "acceptance": list(goal.acceptance),
        } for goal in goals],
        "findings": findings,
        "summary": {
            "total": len(goals), "active": len(active),
            "done": sum(goal.status == "done" for goal in goals),
        },
    }
