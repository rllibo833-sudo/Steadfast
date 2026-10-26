from __future__ import annotations

from pathlib import Path
from typing import Any

from .checks import evidence_findings, product_code_lines
from .contracts import contract_findings, validate_policy_file
from .policy import load_policy


def release_findings(repo: Path, report: dict[str, Any] | None = None) -> list[dict[str, str]]:
    """Evaluate release prerequisites without publishing or modifying a release."""
    findings: list[dict[str, str]] = validate_policy_file(repo)
    try:
        policy = load_policy(repo)
    except (FileNotFoundError, ValueError, OSError):
        return findings
    findings.extend(evidence_findings(repo, policy))
    findings.extend(contract_findings(repo, policy))
    lines, files = product_code_lines(repo, policy)
    budget = policy.get("product_code_budget", 20000)
    if lines > budget:
        findings.append({
            "severity": "error", "code": "RELEASE_BUDGET_EXCEEDED",
            "path": "src",
            "message": f"Release blocked: {lines} implementation lines exceed budget {budget}.",
        })
    if not files:
        findings.append({
            "severity": "warning", "code": "NO_IMPLEMENTATION_FILES",
            "path": "src", "message": "No files matched implementation_paths.",
        })
    changelog = repo / "CHANGELOG.md"
    if not changelog.is_file() or len(changelog.read_text(encoding="utf-8").strip()) < 30:
        findings.append({
            "severity": "warning", "code": "CHANGELOG_NOT_READY",
            "path": "CHANGELOG.md",
            "message": "Release notes are missing or too short to review.",
        })
    if report is not None and not report.get("passed", False):
        findings.append({
            "severity": "error", "code": "AUDIT_FAILED",
            "path": "audit", "message": "The supplied audit report contains error findings.",
        })
    return findings


def release_report(repo: Path, audit_report: dict[str, Any] | None = None) -> dict[str, Any]:
    findings = release_findings(repo, audit_report)
    errors = sum(item["severity"] == "error" for item in findings)
    warnings = sum(item["severity"] == "warning" for item in findings)
    return {
        "tool": "steadfast", "check": "release-readiness",
        "repository": str(repo), "findings": findings,
        "summary": {"errors": errors, "warnings": warnings},
        "ready": errors == 0,
    }
