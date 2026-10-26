from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .baseline import compare_baseline, write_baseline
from .checks import run_audit, scope_findings, evidence_findings, agent_scope_findings
from .docsync import docs_sync_report
from .gitops import changed_paths
from .goals import goal_report
from .inventory import inventory_report
from .history import read_history, record_run
from .integrations import SUPPORTED_AGENTS, install_integration, integration_status, run_hook
from .policy import init_policy, load_policy
from .pipeline import run_pipeline
from .release import release_report
from .report import render_json, render_markdown
from .sarif import render_sarif
from .security import security_findings, workflow_findings
from .workcycle import attach_evidence, block_cycle, complete_cycle, cycle_history, cycle_status, start_cycle, verify_cycle
from .findings import finding_history, finding_metrics, list_findings, resolve_finding, scan_findings, triage_finding
from .planner import execution_plan, explain_goal
from .automations import automation_history, list_automations, run_automation
from .code_truth import code_truth_report
from .session_ledger import session_report, verify_session_ledger
from .evidence_bundle import build_evidence_bundle, verify_evidence_bundle
from .impact import analyze_change_impact
from .workorders import close_work_order, issue_work_order, list_work_orders, show_work_order, verify_work_order
from .ecosystem import ecosystem_report
from .trust import evaluate_component_policy
from .sitecheck import site_check_report
from .control_plane import verification_report


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(
        prog="steadfast",
        description="Evidence-based governance for coding-agent repositories.",
    )
    root.add_argument("--repo", default=".", help="Repository root (default: current directory)")
    commands = root.add_subparsers(dest="command", required=True)
    commands.add_parser("init", help="Create starter policy, goal, and evidence files")
    commands.add_parser("verify", help="Run unified control-plane checks")
    audit = commands.add_parser("audit", help="Run configured governance checks")
    audit.add_argument("--base", help="Compare changes against BASE...HEAD")
    scope = commands.add_parser("scope-check", help="Check changed paths against allowlist")
    scope.add_argument("--changed", nargs="*", help="Explicit changed paths; otherwise inspect Git")
    agent_check = commands.add_parser("agent-check", help="Enforce role-specific changed-path rules for code or media agents")
    agent_check.add_argument("--role", choices=("code", "media"), required=True)
    agent_check.add_argument("--changed", nargs="*", help="Explicit changed paths; otherwise inspect Git")
    evidence = commands.add_parser("evidence-check", help="Check required verification evidence")
    evidence.add_argument("--evidence", help="Check only this evidence file")
    report = commands.add_parser("report", help="Print a complete audit report")
    report.add_argument("--format", choices=("markdown", "json", "sarif"), default="markdown")
    commands.add_parser("inventory", help="Inventory repository files and implementation budget")
    commands.add_parser("release-check", help="Evaluate release prerequisites without publishing")
    commands.add_parser("goal-check", help="Validate goal files and dependency graph")
    plan = commands.add_parser("plan", help="Build a dependency-aware execution queue from goals and open findings")
    plan.add_argument("--include-proposed", action="store_true", help="Include proposed goals in the unready queue")
    plan.add_argument("--goal", help="Explain one goal and its dependencies instead of showing the full queue")
    commands.add_parser("docs-check", help="Check CLI/documentation and package entrypoint alignment")
    impact = commands.add_parser("impact-check", help="Analyze changed files, test/doc relationships and review gates")
    impact.add_argument("--base", help="Compare committed changes against BASE...HEAD")
    impact.add_argument("--changed", nargs="*", help="Explicit changed paths; otherwise inspect Git")
    commands.add_parser("code-truth", help="Derive product facts from source code and flag stale documented CLI examples")
    commands.add_parser("security-check", help="Scan source patterns and GitHub workflow trust boundaries")
    site_check = commands.add_parser("site-check", help="Audit a local static website for search discovery and broken internal links")
    site_check.add_argument("site", help="Repository-relative static site directory, such as docs/ or site/")
    serve = commands.add_parser("serve", help="Open the local read-only Project Console in a browser")
    serve.add_argument("--host", default="127.0.0.1", help="Loopback host (remote hosts are refused)")
    serve.add_argument("--port", type=int, default=8765, help="Local HTTP port (0 selects an available port)")
    integrate = commands.add_parser("integrate", help="Install coding-agent guidance without overwriting existing files")
    integrate.add_argument("--agent", choices=("claude", "cursor", "codex", "all"), default="all")
    integrate.add_argument("--overwrite", action="store_true", help="Explicitly replace existing integration files")
    commands.add_parser("integration-status", help="Show installed coding-agent integrations")
    commands.add_parser("discover", help="Emit a machine-readable capability map for any agent or developer")
    ecosystem = commands.add_parser("ecosystem", help="Inventory repository skills and MCP integrations with owner-controlled trust status")
    ecosystem.add_argument("--strict", action="store_true", help="Return failure when any MCP server is not explicitly trusted")
    trust_check = commands.add_parser("trust-check", help="Evaluate owner-approved permissions for a skill, plugin, or MCP server without executing it")
    trust_check.add_argument("--kind", choices=("skill", "plugin", "mcp"), required=True)
    trust_check.add_argument("--name", required=True)
    trust_check.add_argument("--permission", action="append", default=[], help="Requested permission; repeat for multiple permissions")
    commands.add_parser("mcp-server", help="Serve read-only Steadfast tools over the standard MCP stdio protocol")
    onboard = commands.add_parser("onboard", help="Set up Steadfast policy and selected coding-agent integrations in one command")
    onboard.add_argument("--agent", choices=("claude", "cursor", "codex", "all"), default="all")
    automations = commands.add_parser("automations", help="List and run local, allowlisted automation workflows")
    automation_sub = automations.add_subparsers(dest="automation_action", required=True)
    automation_sub.add_parser("list", help="List available workflows and built-in actions")
    automation_run = automation_sub.add_parser("run", help="Run one named workflow")
    automation_run.add_argument("workflow_id")
    automation_hist = automation_sub.add_parser("history", help="Show recent automation runs")
    automation_hist.add_argument("--limit", type=int, default=20)
    commands.add_parser("agent-hook", help="Read one JSON tool event from stdin and emit an allow/block decision")
    pipeline = commands.add_parser("pipeline", help="Execute a validated dependency-aware verification pipeline")
    pipeline.add_argument("--manifest", default=".steadfast/pipeline.json", help="Repository-relative pipeline JSON manifest")
    pipeline.add_argument("--workers", type=int, default=4, help="Maximum concurrent independent steps (1-16)")
    pipeline.add_argument("--record", help="Append the result to a repository-relative JSONL history file")
    bundle = commands.add_parser("evidence-bundle", help="Build or verify a portable governance evidence package")
    bundle_sub = bundle.add_subparsers(dest="bundle_action", required=True)
    bundle_build = bundle_sub.add_parser("build", help="Collect current checks and build a hash-verified ZIP")
    bundle_build.add_argument("--output", help="Repository-relative output path (default: .steadfast/artifacts/...)")
    bundle_build.add_argument("--overwrite", action="store_true", help="Replace an existing output bundle")
    bundle_verify = bundle_sub.add_parser("verify", help="Verify bundle structure and artifact hashes")
    bundle_verify.add_argument("path", help="Repository-relative bundle path")
    sessions = commands.add_parser("sessions", help="Inspect coding-agent session history and integrity")
    session_sub = sessions.add_subparsers(dest="session_action", required=True)
    session_list = session_sub.add_parser("list", help="Summarize agent sessions and tool decisions")
    session_list.add_argument("--limit", type=int, default=100)
    session_list.add_argument("--session-id", default="")
    session_sub.add_parser("verify", help="Verify the append-only session ledger hash chain")
    history = commands.add_parser("pipeline-history", help="Inspect recent recorded pipeline executions")
    history.add_argument("--history", default=".steadfast/runs.jsonl", help="Repository-relative JSONL history file")
    history.add_argument("--limit", type=int, default=20, help="Maximum recent runs to display (1-1000)")
    history.add_argument("--status", choices=("all", "passed", "failed"), default="all", help="Filter runs by outcome")
    work_order = commands.add_parser("work-order", help="Issue and verify bounded agent task contracts")
    work_order_sub = work_order.add_subparsers(dest="work_order_action", required=True)
    work_order_issue = work_order_sub.add_parser("issue", help="Issue a scoped contract from a configured goal")
    work_order_issue.add_argument("goal_id")
    work_order_issue.add_argument("--owner", default="")
    work_order_issue.add_argument("--ttl-minutes", type=int, default=240)
    work_order_issue.add_argument("--scope", nargs="*", help="Narrow scope to repository-relative paths or directory/** patterns")
    work_order_list = work_order_sub.add_parser("list", help="List current work orders")
    work_order_list.add_argument("--limit", type=int, default=100)
    work_order_show = work_order_sub.add_parser("show", help="Show a work order contract")
    work_order_show.add_argument("order_id")
    work_order_verify = work_order_sub.add_parser("verify", help="Run pipeline and validate scope against the issued contract")
    work_order_verify.add_argument("order_id")
    work_order_close = work_order_sub.add_parser("close", help="Close a work order after passing verification")
    work_order_close.add_argument("order_id")
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
        if args.command == "verify":
            result = verification_report(repo)
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 0 if result["passed"] else 1

        if args.command == "init":
            created = init_policy(repo)
            if created:
                print("Created:\n" + "\n".join(f"- {path}" for path in created))
            else:
                print("Policy files already exist; nothing overwritten.")
            return 0

        if args.command == "mcp-server":
            from .mcp_server import serve_stdio
            return serve_stdio(repo)

        if args.command == "serve":
            from .dashboard import serve_dashboard
            serve_dashboard(repo, host=args.host, port=args.port)
            return 0

        if args.command == "integrate":
            agents = ("claude", "cursor", "codex") if args.agent == "all" else (args.agent,)
            result = [install_integration(repo, agent, overwrite=args.overwrite) for agent in agents]
            print(json.dumps({"integrations": result}, indent=2, ensure_ascii=False))
            return 0
        if args.command == "onboard":
            created = init_policy(repo)
            agents = ("claude", "cursor", "codex") if args.agent == "all" else (args.agent,)
            integrations = [install_integration(repo, agent, overwrite=False) for agent in agents]
            result = {
                "status": "ready",
                "created_foundation_files": [Path(path).as_posix() for path in created],
                "integrations": integrations,
                "preserved_existing_files": sorted(path for item in integrations for path in item["preserved"]),
                "next_command": "steadfast --repo . discover",
                "external_registration_required": False,
                "note": "This prepares repository-local guidance and hooks; it does not grant GitHub permissions or register third-party accounts.",
            }
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 0


        if args.command == "automations":
            if args.automation_action == "list": result = list_automations(repo)
            elif args.automation_action == "run": result = run_automation(repo, args.workflow_id)
            else: result = automation_history(repo, args.limit)
            print(json.dumps(result, indent=2, ensure_ascii=False))
            if args.automation_action == "run" and result.get("status") != "passed": return 1
            return 0

        if args.command == "integration-status":
            print(json.dumps(integration_status(repo), indent=2, ensure_ascii=False))
            return 0

        if args.command == "trust-check":
            result = evaluate_component_policy(repo, args.kind, args.name, args.permission)
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 0 if result["decision"] == "allow" else 1

        if args.command == "ecosystem":
            result = ecosystem_report(repo)
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 1 if args.strict and result["untrusted_mcp_servers"] else 0

        if args.command == "site-check":
            result = site_check_report(repo, args.site)
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 1 if result["errors"] else 0

        if args.command == "discover":
            skill_files = sorted(
                path.relative_to(repo).as_posix()
                for base in (repo / "skills", repo / ".agents" / "skills")
                if base.is_dir()
                for path in base.rglob("SKILL.md")
                if path.is_file()
            )
            workflow_files = sorted(
                path.relative_to(repo).as_posix()
                for path in (repo / ".github" / "workflows").glob("*.yml")
            ) if (repo / ".github" / "workflows").is_dir() else []
            from .ecosystem import ecosystem_report
            ecosystem = ecosystem_report(repo)
            result = {
                "schema_version": 1,
                "product": "Steadfast",
                "purpose": "Evidence-based repository governance and ecosystem discovery for coding agents and developers",
                "repository_root": str(repo),
                "ecosystem": {
                    "skills": ecosystem["skills"],
                    "skill_entry_points": ecosystem["installed_extensions"]["skills"],
                    "plugins": ecosystem["installed_extensions"]["plugins"],
                    "component_policy": ecosystem["component_policy"],
                    "mcp_status": {
                        "repository_servers": ecosystem["mcp_servers"],
                        "installed_server_entry_points": ecosystem["installed_extensions"]["mcp_servers"],
                        "trust_status": ecosystem["status"],
                    },
                    "installed_extensions": ecosystem["installed_extensions"],
                    "integration_status": ecosystem["integrations"],
                    "trust_status": ecosystem["status"],
                },
                "entrypoints": {
                    "agent_instructions": "AGENTS.md" if (repo / "AGENTS.md").is_file() else None,
                    "policy": ".steadfast/policy.json" if (repo / ".steadfast" / "policy.json").is_file() else None,
                    "goal": ".steadfast/goal.md" if (repo / ".steadfast" / "goal.md").is_file() else None,
                    "pipeline": ".steadfast/pipeline.json" if (repo / ".steadfast" / "pipeline.json").is_file() else None,
                },
                "supported_integrations": list(SUPPORTED_AGENTS),
                "installed_integrations": integration_status(repo),
                "skills": skill_files,
                "github_workflows": workflow_files,
                "commands": {
                    "quick_start": "steadfast --repo . discover",
                    "inspect_policy": "steadfast --repo . report --format json",
                    "check_scope": "steadfast --repo . scope-check",
                    "run_pipeline": "steadfast --repo . pipeline",
                    "agent_hook_protocol": "JSON on stdin; JSON decision on stdout via steadfast --repo . agent-hook",
                    "issue_scoped_work_order": "steadfast --repo . work-order issue GOAL_ID --scope src/** tests/**",
                    "verify_work_order": "steadfast --repo . work-order verify ORDER_ID",
                    "impact_check": "steadfast --repo . impact-check",
                    "evidence_bundle": "steadfast --repo . evidence-bundle build",
                },
                "cost_policy": {
                    "external_services_required": False,
                    "paid_runner_required": False,
                    "workflow_count_is_not_expanded_by_discover": True,
                },
            }
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 0

        if args.command == "agent-hook":
            return run_hook(repo)

        policy = load_policy(repo)
        if args.command == "agent-check":
            paths = args.changed if args.changed is not None else changed_paths(repo)
            findings = agent_scope_findings(policy, args.role, paths)
            print(json.dumps({"role": args.role, "checked_paths": paths, "passed": not _has_errors(findings), "findings": findings}, indent=2, ensure_ascii=False))
            return 1 if _has_errors(findings) else 0

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

        if args.command == "plan":
            result = explain_goal(repo, args.goal, include_proposed=True) if args.goal else execution_plan(repo, include_proposed=args.include_proposed)
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 1 if result.get("graph_errors") or result.get("plan_summary", {}).get("graph_errors") else 0

        if args.command == "goal-check":
            result = goal_report(repo, policy)
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 1 if _has_errors(result["findings"]) else 0

        if args.command == "impact-check":
            result = analyze_change_impact(repo, base=args.base, paths=args.changed)
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 0 if result.get("passed") else 1

        if args.command == "code-truth":
            result = code_truth_report(repo)
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 0 if result["passed"] else 1

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

        if args.command == "evidence-bundle":
            result = (build_evidence_bundle(repo, args.output, overwrite=args.overwrite)
                      if args.bundle_action == "build"
                      else verify_evidence_bundle(repo, args.path))
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 0 if result.get("valid", result.get("status") == "built") else 1

        if args.command == "sessions":
            result = verify_session_ledger(repo) if args.session_action == "verify" else session_report(repo, args.limit, args.session_id)
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 0 if args.session_action != "verify" or result.get("valid") else 1

        if args.command == "pipeline-history":
            result = read_history(repo, args.history, limit=args.limit, status=args.status)
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 0

        if args.command == "work-order":
            if args.work_order_action == "issue":
                result = issue_work_order(repo, args.goal_id, owner=args.owner,
                                          ttl_minutes=args.ttl_minutes, scope_paths=args.scope)
            elif args.work_order_action == "list":
                result = list_work_orders(repo, args.limit)
            elif args.work_order_action == "show":
                result = show_work_order(repo, args.order_id)
            elif args.work_order_action == "verify":
                result = verify_work_order(repo, args.order_id)
            else:
                result = close_work_order(repo, args.order_id)
            print(json.dumps(result, indent=2, ensure_ascii=False))
            if args.work_order_action == "verify":
                return 0 if result.get("passed") else 1
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
