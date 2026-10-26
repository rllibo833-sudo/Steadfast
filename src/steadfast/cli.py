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
from .policy import init_policy, load_policy
from .release import release_report
from .report import render_json, render_markdown
from .sarif import render_sarif


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
