from __future__ import annotations
import argparse, json, sys
from pathlib import Path
from .checks import run_audit, scope_findings, evidence_findings
from .gitops import changed_paths
from .policy import init_policy, load_policy
from .report import render_json, render_markdown

def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="steadfast", description="Evidence-based governance for coding-agent repositories.")
    p.add_argument("--repo", default=".", help="Repository root (default: current directory)")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("init", help="Create starter policy, goal, and evidence files")
    audit = sub.add_parser("audit", help="Run all configured governance checks")
    audit.add_argument("--base", help="Compare changes against BASE...HEAD")
    scope = sub.add_parser("scope-check", help="Check changed paths against allowlist")
    scope.add_argument("--changed", nargs="*", help="Explicit changed paths; otherwise inspect Git working tree")
    ev = sub.add_parser("evidence-check", help="Check required verification evidence")
    ev.add_argument("--evidence", help="Check only this evidence file")
    rep = sub.add_parser("report", help="Print complete audit report")
    rep.add_argument("--format", choices=("markdown","json"), default="markdown")
    return p

def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    repo = Path(args.repo).resolve()
    try:
        if args.command == "init":
            created = init_policy(repo)
            print("Created:\n" + "\n".join(f"- {p}" for p in created) if created else "Policy files already exist; nothing overwritten.")
            return 0
        policy = load_policy(repo)
        if args.command == "scope-check":
            paths = args.changed if args.changed is not None else changed_paths(repo)
            findings = scope_findings(repo, policy, paths)
            for f in findings:
                print(f"{f['severity'].upper()} {f['code']}: {f['path']} — {f['message']}")
            print(f"Scope check: {'PASS' if not findings else 'FAIL'} ({len(paths)} paths)")
            return 0 if not findings else 1
        if args.command == "evidence-check":
            if args.evidence:
                policy["required_evidence"] = [args.evidence]
            findings = evidence_findings(repo, policy)
            for f in findings:
                print(f"{f['severity'].upper()} {f['code']}: {f['path']} — {f['message']}")
            print(f"Evidence check: {'PASS' if not any(x['severity']=='error' for x in findings) else 'FAIL'}")
            return 0 if not any(x["severity"] == "error" for x in findings) else 1
        report = run_audit(repo, getattr(args, "base", None))
        output = render_json(report) if args.command == "report" and args.format == "json" else render_markdown(report)
        print(output)
        return 0 if report["passed"] else 1
    except (FileNotFoundError, ValueError, OSError, json.JSONDecodeError, RuntimeError) as exc:
        print(f"steadfast: error: {exc}", file=sys.stderr)
        return 2

if __name__ == "__main__":
    raise SystemExit(main())
