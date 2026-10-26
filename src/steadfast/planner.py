from __future__ import annotations

from collections import defaultdict, deque
from pathlib import Path
from typing import Any

from .findings import list_findings
from .goals import goal_report
from .policy import load_policy
from .workcycle import cycle_status

PRIORITY_WEIGHT = {"critical": 100, "high": 60, "medium": 25, "low": 5}
CLOSED_FINDING_STATES = {"fixed", "false_positive"}


def _dependency_order(goals: list[dict[str, Any]]) -> tuple[list[str], list[str]]:
    by_id = {str(goal["id"]): goal for goal in goals}
    indegree = {goal_id: 0 for goal_id in by_id}
    children: dict[str, list[str]] = defaultdict(list)
    errors: list[str] = []
    for goal_id, goal in by_id.items():
        for dependency in goal.get("depends_on", []):
            if dependency not in by_id:
                errors.append(f"{goal_id} depends on missing goal {dependency}")
                continue
            indegree[goal_id] += 1
            children[dependency].append(goal_id)
    ready = deque(sorted(goal_id for goal_id, degree in indegree.items() if degree == 0))
    order: list[str] = []
    while ready:
        goal_id = ready.popleft()
        order.append(goal_id)
        for child in sorted(children[goal_id]):
            indegree[child] -= 1
            if indegree[child] == 0:
                ready.append(child)
    if len(order) != len(by_id):
        errors.extend(f"dependency cycle prevents scheduling goal {goal_id}" for goal_id, degree in indegree.items() if degree)
    return order, errors


def _goal_state(goal: dict[str, Any], by_id: dict[str, dict[str, Any]]) -> tuple[bool, list[str]]:
    waiting = []
    for dependency in goal.get("depends_on", []):
        upstream = by_id.get(dependency)
        if upstream is None:
            waiting.append(f"missing dependency: {dependency}")
        elif upstream.get("status") != "done":
            waiting.append(f"waiting for {dependency} ({upstream.get('status', 'unknown')})")
    return not waiting, waiting


def _risk_for_goal(goal: dict[str, Any], findings: list[dict[str, Any]]) -> tuple[int, list[str]]:
    acceptance = [str(x).casefold() for x in goal.get("acceptance", [])]
    goal_tokens = set((str(goal.get("id", "")) + " " + str(goal.get("title", ""))).casefold().replace("/", " ").replace("_", " ").replace("-", " ").split())
    related: list[dict[str, Any]] = []
    for finding in findings:
        if finding.get("state") in CLOSED_FINDING_STATES:
            continue
        path = str(finding.get("path", ""))
        code = str(finding.get("code", "")).casefold()
        message = str(finding.get("message", "")).casefold()
        path_tokens = set(path.casefold().replace("/", " ").replace("_", " ").replace("-", " ").replace(".", " ").split())
        finding_tokens = set((code + " " + message).replace("_", " ").replace("-", " ").split())
        same_path = any(token in path_tokens for token in goal_tokens if len(token) > 2)
        same_language = any(any(token in finding_tokens for token in criterion.split() if len(token) > 4) for criterion in acceptance)
        if same_path or same_language:
            related.append(finding)
    score = sum(PRIORITY_WEIGHT.get(str(item.get("priority", "medium")), 25) for item in related)
    return score, [str(item.get("id", item.get("code", "unknown"))) for item in related]


def execution_plan(repo: Path, *, include_proposed: bool = False) -> dict[str, Any]:
    """Build a dependency-aware, risk-informed execution queue without mutating files."""
    root = repo.resolve()
    policy = load_policy(root)
    goal_result = goal_report(root, policy)
    goals = goal_result.get("goals", [])
    order, graph_errors = _dependency_order(goals)
    by_id = {str(goal["id"]): goal for goal in goals}
    ledger = list_findings(root, limit=1000)
    findings = ledger.get("findings", [])
    active_cycle = cycle_status(root).get("task")
    active_ids = {str(active_cycle.get("goal_id"))} if active_cycle else set()
    candidates: list[dict[str, Any]] = []
    for goal_id in order:
        goal = by_id[goal_id]
        status = str(goal.get("status", "proposed"))
        if status in {"done", "cancelled"}:
            continue
        if status == "proposed" and not include_proposed:
            continue
        ready, waiting = _goal_state(goal, by_id)
        if goal_id in active_ids:
            ready, waiting = False, ["already active in the work cycle"]
        risk_score, related = _risk_for_goal(goal, findings)
        candidates.append({
            "goal_id": goal_id, "title": goal.get("title", goal_id),
            "goal_status": status, "goal_path": goal.get("path", ""),
            "depends_on": list(goal.get("depends_on", [])),
            "acceptance_count": len(goal.get("acceptance", [])),
            "ready": ready and status in {"ready", "active"},
            "waiting_reasons": waiting,
            "risk_score": risk_score, "related_finding_ids": related,
            "recommended_action": (
                "continue_active_cycle" if goal_id in active_ids else
                "start_work_cycle" if ready and status in {"ready", "active"} else
                "resolve_dependencies" if waiting else
                "review_goal_readiness"
            ),
        })
    ready_goals = [item for item in candidates if item["ready"]]
    ready_goals.sort(key=lambda item: (-item["risk_score"], order.index(item["goal_id"])))
    for index, item in enumerate(ready_goals, 1):
        item["execution_rank"] = index
    ranks = {item["goal_id"]: item["execution_rank"] for item in ready_goals}
    for item in candidates:
        if item["goal_id"] in ranks:
            item["execution_rank"] = ranks[item["goal_id"]]
        else:
            item["execution_rank"] = None
    return {
        "schema_version": 1,
        "mode": "read_only_plan",
        "goal_count": len(goals),
        "candidate_count": len(candidates),
        "ready_count": len(ready_goals),
        "active_cycle": active_cycle,
        "graph_errors": graph_errors,
        "goal_findings": goal_result.get("findings", []),
        "execution_queue": ready_goals,
        "blocked_or_unready": [item for item in candidates if not item["ready"]],
        "ordering": "dependency order first; among currently ready goals, higher related open-risk weight first",
        "risk_model": "heuristic token/path matching for triage only; not a causal link or automated severity verdict",
    }


def explain_goal(repo: Path, goal_id: str, *, include_proposed: bool = True) -> dict[str, Any]:
    """Return the exact dependencies, acceptance criteria, and risk signals for one goal."""
    plan = execution_plan(repo, include_proposed=include_proposed)
    match = next((item for item in plan["execution_queue"] + plan["blocked_or_unready"] if item["goal_id"] == goal_id), None)
    if match is None:
        raise ValueError(f"goal {goal_id!r} was not found or is already closed")
    policy = load_policy(repo.resolve())
    report = goal_report(repo.resolve(), policy)
    goal = next((item for item in report.get("goals", []) if item["id"] == goal_id), None)
    if goal is None:
        raise ValueError(f"goal {goal_id!r} does not exist")
    return {"plan_item": match, "acceptance_criteria": goal.get("acceptance", []),
            "dependencies": [next((x for x in report["goals"] if x["id"] == dep), {"id": dep, "status": "missing"})
                             for dep in goal.get("depends_on", [])],
            "plan_summary": {"ready_count": plan["ready_count"], "candidate_count": plan["candidate_count"],
                             "graph_errors": plan["graph_errors"]}}
