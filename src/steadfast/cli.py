from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .baseline import compare_baseline, write_baseline
from .checks import run_audit, scope_findings, evidence_findings
from .docsync import docs_sync_report
from .gitops import changed_paths
from .goals import goal_report
from .inventory import inventory_report
from .history import read_history, record_run
from .integrations import install_integration, integration_status, run_hook
from .policy import init_policy, load_policy
from .pipeline import run_pipeline
from .release import release_report
from .report import render_json, render_markdown
from .sarif import render_sarif
from .security import security_findings, workflow_findings
from .workcycle import attach_evidence, block_cycle, complete_cycle, cycle_history, cycle_status, start_cycle, verify_cycle
from .findings import finding_history, finding_metrics, list_findings, resolve_finding, scan_findings, triage_finding


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(
        prog="steadfast",
        description="Evidence-based governance for coding-agent repositories.",
    )
    root.add_argument("--repo", default=".", help="Repository root (default: current directory)")
    commands = root.add_subparsers(dest="command", required=True)
    commands.add_parser("init", help="Create starter policy, goal, and evidence files")
    audit = commands.add_parser("audit", help="Run configured governance checks")
    audit.add_argument("--base", help="Compare changes against BASE...HEAD")
    scope = commands.add_parser("scope-check", help="Check changed paths against allowlist")
    scope.add_argument("--changed", nargs="*", help="Explicit changed paths; otherwise inspect Git")
    evidence = commands.add_parser("evidence-check", help="Check required verification evidence")
    evidence.add_argument("--evidence", help="Check only this evidence file")
    report = commands.add_parser("report", help="Print a complete audit report")
    report.add_argument("--format", choices=("markdown", "json", "sarif"), default="markdown")
    commands.add_parser("inventory", help="Inventory repository files and implementation budget")
    commands.add_parser("release-check", help="Evaluate release prerequisites without publishing")
    commands.add_parser("goal-check", help="Validate goal files and dependency graph")
    commands.add_parser("docs-check", help="Check CLI/documentation and package entrypoint alignment")
    commands.add_parser("security-check", help="Scan source patterns and GitHub workflow trust boundaries")
    serve = commands.add_parser("serve", help="Open the local read-only Project Console in a browser")
    serve.add_argument("--host", default="127.0.0.1", help="Loopback host (remote hosts are refused)")
    serve.add_argument("--port", type=int, default=8765, help="Local HTTP port (0 selects an available port)")
    integrate = commands.add_parser("integrate", help="Install coding-agent guidance without overwriting existing files")
    integrate.add_argument("--agent", choices=("claude", "cursor", "codex", "all"), default="all")
    integrate.add_argument("--overwrite", action="store_true", help="Explicitly replace existing integration files")
    commands.add_parser("integration-status", help="Show installed coding-agent integrations")
    commands.add_parser("agent-hook", help="Read one JSON tool event from stdin and emit an allow/block decision")
    pipeline = commands.add_parser("pipeline", help="Execute a validated dependency-aware verification pipeline")
    pipeline.add_argument("--manifest", default=".steadfast/pipeline.json", help="Repository-relative pipeline JSON manifest")
    pipeline.add_argument("--workers", type=int, default=4, help="Maximum concurrent independent steps (1-16)")
    pipeline.add_argument("--record", help="Append the result to a repository-relative JSONL history file")
    history = commands.add_parser("pipeline-history", help="Inspect recent recorded pipeline executions")
    history.add_argument("--history", default=".steadfast/runs.jsonl", help="Repository-relative JSONL history file")
    history.add_argument("--limit", type=int, default=20, help="Maximum recent runs to display (1-1000)")
    history.add_argument("--status", choices=("all", "passed", "failed"), default="all", help="Filter runs by outcome")
    cycle = commands.add_parser("cycle", help="Run an evidence-gated task work cycle")
    sub = cycle.add_subparsers(dest="cycle_action", required=True)
    start = sub.add_parser("start", help="Start a configured goal"); start.add_argument("goal_id"); start.add_argument("--title", default="")
    sub.add_parser("status", help="Show current task")
    sub.add_parser("verify", help="Run configured pipeline and scope checks")
    sub.add_parser("complete", help="Complete only after verification and evidence pass")
    block = sub.add_parser("block", help="Block a task"); block.add_argument("reason")
    proof = sub.add_parser("evidence", help="Attach evidence to an acceptance criterion"); proof.add_argument("criterion_id"); proof.add_argument("path"); proof.add_argument("--note", default="")
    history = sub.add_parser("history", help="Read work-cycle event history"); history.add_argument("--limit", type=int, default=20)
    findings = commands.add_parser("findings", help="Manage the durable audit finding lifecycle")
    finding_sub = findings.add_subparsers(dest="finding_action", required=True)
    finding_sub.add_parser("scan", help="Refresh live findings and reconcile resolved items")
    finding_list = finding_sub.add_parser("list", help="List findings with filters")
    finding_list.add_argument("--state", choices=("all", "open", "triaged", "accepted", "fixed", "false_positive"), default="all")
    finding_list.add_argument("--priority", choices=("all", "critical", "high", "medium", "low"), default="all")
    finding_list.add_argument("--query", default="")
    finding_list.add_argument("--limit", type=int, default=200)
    finding_triage = finding_sub.add_parser("triage", help="Assign owner, priority, due date or state")
    finding_triage.add_argument("finding_id")
    finding_triage.add_argument("--state", choices=("open", "triaged", "accepted"))
    finding_triage.add_argument("--owner")
    finding_triage.add_argument("--priority", choices=("critical", "high", "medium", "low"))
    finding_triage.add_argument("--due-date", default=None)
    finding_triage.add_argument("--note", default="")
    finding_resolve = finding_sub.add_parser("resolve", help="Record a reason for resolving a finding")
    finding_resolve.add_argument("finding_id")
    finding_resolve.add_argument("resolution")
    finding_resolve.add_argument("--false-positive", action="store_true")
    finding_hist = finding_sub.add_parser("history", help="Inspect hash-chained finding events")
    finding_hist.add_argument("--finding-id", default="")
    finding_hist.add_argument("--limit", type=int, default=100)
    finding_sub.add_parser("metrics", help="Show open risk, accepted risk and overdue items")
    baseline_check = commands.add_parser("baseline-check", help="Compare current audit with a saved baseline")
    baseline_check.add_argument("--base", help="Compare changes against BASE...HEAD")
    baseline_update = commands.add_parser("baseline-update", help="Explicitly replace the audit baseline")
    baseline_update.add_argument("--base", help="Compare changes against BASE...HEAD")
    return root


def _print_findings(findings: list[dict[str, str]]) -> None:
    for finding in findings:
        print(
            f"{finding['severity'].upper()} {finding['code']}: "
            f"{finding['path']} — {finding['message']}"
        )


def _has_errors(findings: list[dict[str, str]]) -> bool:
    return any(item.get("severity") == "error" for item in findings)


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    repo = Path(args.repo).resolve()
    try:
        if args.command == "init":
            created = init_policy(repo)
            if created:
                print("Created:\n" + "\n".join(f"- {path}" for path in created))
            else:
                print("Policy files already exist; nothing overwritten.")
            return 0

        if args.command == "serve":
            from .dashboard import serve_dashboard
            serve_dashboard(repo, host=args.host, port=args.port)
            return 0

        if args.command == "integrate":
            agents = ("claude", "cursor", "codex") if args.agent == "all" else (args.agent,)
            result = [install_integration(repo, agent, overwrite=args.overwrite) for agent in agents]
            print(json.dumps({"integrations": result}, indent=2, ensure_ascii=False))
            return 0

        if args.command == "integration-status":
            print(json.dumps(integration_status(repo), indent=2, ensure_ascii=False))
            return 0

        if args.command == "agent-hook":
            return run_hook(repo)

        policy = load_policy(repo)
        if args.command == "scope-check":
            paths = args.changed if args.changed is not None else changed_paths(repo)
            findings = scope_findings(repo, policy, paths)
            _print_findings(findings)
            print(f"Scope check: {'FAIL' if findings else 'PASS'} ({len(paths)} paths)")
            return 1 if _has_errors(findings) else 0

        if args.command == "evidence-check":
            if args.evidence:
                policy["required_evidence"] = [args.evidence]
            findings = evidence_findings(repo, policy)
            _print_findings(findings)
            print(f"Evidence check: {'FAIL' if _has_errors(findings) else 'PASS'}")
            return 1 if _has_errors(findings) else 0

        if args.command == "inventory":
            print(json.dumps(inventory_report(repo), indent=2, ensure_ascii=False))
            return 0

        if args.command == "release-check":
            result = release_report(repo)
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 0 if result["ready"] else 1

        if args.command == "goal-check":
            result = goal_report(repo, policy)
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 1 if _has_errors(result["findings"]) else 0

        if args.command == "docs-check":
            result = docs_sync_report(repo)
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 1 if _has_errors(result["findings"]) else 0

        if args.command == "security-check":
            findings = security_findings(repo, policy) + workflow_findings(repo)
            _print_findings(findings)
            print(f"Security check: {'FAIL' if _has_errors(findings) else 'PASS'} ({len(findings)} findings)")
            return 1 if _has_errors(findings) else 0

        if args.command == "pipeline":
            result = run_pipeline(repo, Path(args.manifest), max_workers=args.workers)
            if args.record:
                record = record_run(repo, args.record, result)
                result["history_record"] = {"path": args.record, "run_id": record["run_id"]}
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 0 if result["passed"] else 1

        if args.command == "pipeline-history":
            result = read_history(repo, args.history, limit=args.limit, status=args.status)
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 0

        if args.command == "cycle":
            if args.cycle_action == "start": result = start_cycle(repo, args.goal_id, args.title)
            elif args.cycle_action == "status": result = cycle_status(repo)
            elif args.cycle_action == "verify": result = verify_cycle(repo)
            elif args.cycle_action == "complete": result = complete_cycle(repo)
            elif args.cycle_action == "block": result = block_cycle(repo, args.reason)
            elif args.cycle_action == "evidence": result = attach_evidence(repo, args.criterion_id, args.path, args.note)
            else: result = cycle_history(repo, args.limit)
            print(json.dumps(result, indent=2, ensure_ascii=False))
            if args.cycle_action == "verify" and not result.get("passed"): return 1
            return 0

        if args.command == "findings":
            if args.finding_action == "scan":
                result = scan_findings(repo)
            elif args.finding_action == "list":
                result = list_findings(repo, args.state, args.priority, args.query, args.limit)
            elif args.finding_action == "triage":
                result = triage_finding(repo, args.finding_id, args.state, args.owner, args.priority, args.due_date, args.note)
            elif args.finding_action == "resolve":
                result = resolve_finding(repo, args.finding_id, args.resolution, args.false_positive)
            elif args.finding_action == "history":
                result = finding_history(repo, args.finding_id, args.limit)
            else:
                result = finding_metrics(repo)
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 1 if args.finding_action == "scan" and result["summary"].get("audit_passed") is False else 0

        if args.command == "baseline-update":
            destination = write_baseline(repo, getattr(args, "base", None))
            print(f"Baseline written: {destination.relative_to(repo).as_posix()}")
            return 0

        if args.command == "baseline-check":
            result = compare_baseline(repo, getattr(args, "base", None))
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 0 if result.get("ready", False) else 1

        report = run_audit(repo, getattr(args, "base", None))
        if args.command == "report":
            if args.format == "json":
                print(render_json(report))
            elif args.format == "sarif":
                print(render_sarif(report))
            else:
                print(render_markdown(report))
        else:
            print(render_markdown(report))
        return 0 if report["passed"] else 1
    except (FileNotFoundError, ValueError, OSError, json.JSONDecodeError, RuntimeError) as exc:
        print(f"steadfast: error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
