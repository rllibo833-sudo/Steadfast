from __future__ import annotations

import fnmatch
from pathlib import Path
from typing import Any

from .contracts import contract_findings
from .gitops import changed_paths, is_repo
from .policy import load_policy
from .security import security_findings, workflow_findings


def matches(path: str, patterns: list[str]) -> bool:
    """Match a repository-relative path against shell-style policy patterns."""
    for pattern in patterns:
        if fnmatch.fnmatchcase(path, pattern):
            return True
        if pattern.endswith("/**") and path.startswith(pattern[:-2]):
            return True
    return False


IMPLEMENTATION_SUFFIXES = {
    ".py", ".pyi", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".vue", ".svelte",
    ".go", ".rs", ".java", ".kt", ".kts", ".c", ".h", ".cc", ".cpp", ".hpp", ".hh",
    ".cs", ".fs", ".php", ".rb", ".swift", ".scala", ".dart", ".r", ".lua", ".sh", ".cuk",
    ".html", ".css", ".scss", ".sass", ".sql",
}


def product_code_lines(repo: Path, policy: dict[str, Any]) -> tuple[int, list[str]]:
    """Count implementation source lines, excluding generated metadata and data/config files."""
    files: list[str] = []
    total = 0
    ignored = policy.get("ignored_paths", [])
    for path in repo.rglob("*"):
        if not path.is_file() or path.is_symlink():
            continue
        rel = path.relative_to(repo).as_posix()
        if not matches(rel, policy.get("implementation_paths", ["src/**"])):
            continue
        if path.suffix.lower() not in IMPLEMENTATION_SUFFIXES:
            continue
        if any(part.endswith(".egg-info") for part in path.parts) or matches(rel, ignored):
            continue
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeError):
            continue
        total += sum(1 for line in lines if line.strip() and not line.lstrip().startswith("#"))
        files.append(rel)
    return total, sorted(files)


def scope_findings(
    repo: Path, policy: dict[str, Any], paths: list[str] | None = None
) -> list[dict[str, str]]:
    findings = []
    checked_paths = paths if paths is not None else changed_paths(repo)
    allowed = policy.get("allowed_paths", [])
    ignored = policy.get("ignored_paths", [])
    for raw_path in checked_paths:
        path = raw_path.replace("\\", "/").removeprefix("./")
        if path.startswith("/") or ".." in Path(path).parts:
            findings.append({
                "severity": "error", "code": "INVALID_REPOSITORY_PATH",
                "path": raw_path, "message": "Path must stay inside the repository.",
            })
        elif not matches(path, allowed) and not matches(path, ignored):
            findings.append({
                "severity": "error", "code": "SCOPE_OUTSIDE_ALLOWLIST",
                "path": path,
                "message": "Changed path is outside the configured allowlist.",
            })
    return findings


def evidence_findings(repo: Path, policy: dict[str, Any]) -> list[dict[str, str]]:
    findings = []
    for item in policy.get("required_evidence", []):
        path = Path(item)
        if path.is_absolute() or ".." in path.parts:
            findings.append({
                "severity": "error", "code": "INVALID_EVIDENCE_PATH",
                "path": item, "message": "Evidence path must stay inside the repository.",
            })
            continue
        try:
            content = (repo / path).read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            content = ""
        if len(content.strip()) < 40:
            findings.append({
                "severity": "error", "code": "EVIDENCE_MISSING",
                "path": item,
                "message": "Required verification evidence is missing, unreadable, or too short.",
            })
    return findings


def documentation_findings(
    policy: dict[str, Any], paths: list[str]
) -> list[dict[str, str]]:
    implementation_changed = any(
        matches(path, policy.get("implementation_paths", ["src/**"])) for path in paths
    )
    docs_changed = any(
        matches(path, policy.get("documentation_paths", ["README.md", "docs/**", "CHANGELOG.md"]))
        for path in paths
    )
    if implementation_changed and not docs_changed:
        return [{
            "severity": "warning", "code": "DOCS_NOT_CHANGED",
            "path": "src",
            "message": "Implementation changed without a documentation change; review docs for drift.",
        }]
    return []


def run_audit(repo: Path, base: str | None = None) -> dict[str, Any]:
    policy = load_policy(repo)
    paths = changed_paths(repo, base) if is_repo(repo) else []
    count, files = product_code_lines(repo, policy)
    findings = (
        scope_findings(repo, policy, paths)
        + evidence_findings(repo, policy)
        + documentation_findings(policy, paths)
        + contract_findings(repo, policy)
        + security_findings(repo, policy)
        + workflow_findings(repo)
    )
    budget = policy["product_code_budget"]
    if count > budget:
        findings.append({
            "severity": "error", "code": "PRODUCT_CODE_BUDGET_EXCEEDED",
            "path": "src",
            "message": f"{count} counted lines exceed the {budget} line budget.",
        })
    errors = sum(item["severity"] == "error" for item in findings)
    warnings = sum(item["severity"] == "warning" for item in findings)
    info = sum(item["severity"] == "info" for item in findings)
    return {
        "tool": "steadfast", "version": "0.1.0", "repository": str(repo),
        "changed_paths": paths, "product_code_lines": count,
        "product_code_budget": budget, "counted_code_files": len(files),
        "findings": findings,
        "summary": {"errors": errors, "warnings": warnings, "info": info},
        "passed": errors == 0,
    }


MEDIA_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg", ".avif", ".ico", ".mp4", ".webm", ".mov", ".m4v", ".mp3", ".wav", ".ogg", ".flac"}


def agent_scope_findings(policy: dict[str, Any], role: str, paths: list[str]) -> list[dict[str, str]]:
    """Enforce role-specific path rules before accepting an agent change."""
    if role not in {"code", "media"}:
        return [{"severity": "error", "code": "AGENT_ROLE_INVALID", "path": role, "message": "Agent role must be code or media."}]
    rules = policy.get("agent_path_rules", {})
    allowed = rules.get(role, policy.get("allowed_paths", []) if role == "code" else [])
    protected = policy.get("agent_protected_paths", [".steadfast/policy.json", ".github/workflows/**"])
    if not paths:
        return [{"severity": "error", "code": "AGENT_NO_PATHS", "path": "", "message": "No changed paths supplied or detected; refusing to approve an empty scope."}]
    findings: list[dict[str, str]] = []
    for raw_path in paths:
        path = raw_path.replace("\\", "/").removeprefix("./")
        if path.startswith("/") or ".." in Path(path).parts:
            findings.append({"severity": "error", "code": "INVALID_REPOSITORY_PATH", "path": raw_path, "message": "Path must stay inside the repository."})
        elif matches(path, protected):
            findings.append({"severity": "error", "code": "AGENT_PROTECTED_PATH", "path": path, "message": "Protected path requires explicit maintainer handling and is blocked by the agent role gate."})
        elif not matches(path, allowed):
            findings.append({"severity": "error", "code": "AGENT_ROLE_SCOPE_DENIED", "path": path, "message": f"Path is not allowed for the {role} agent role."})
        elif role == "media" and Path(path).suffix.lower() not in MEDIA_SUFFIXES:
            findings.append({"severity": "error", "code": "AGENT_MEDIA_TYPE_DENIED", "path": path, "message": "Media role may add only recognized image, video, or audio asset types."})
    return findings
