from __future__ import annotations

import fnmatch
import subprocess
from pathlib import Path
from typing import Any, Iterable

from .gitops import GitError, changed_paths, is_repo

SOURCE_PATTERNS = (
    "src/**", "lib/**", "native/**", "compiler/**", "runtime/**",
    "app/**", "packages/**/src/**",
)
TEST_PATTERNS = ("tests/**", "test/**", "**/test_*.py", "**/*_test.py", "**/*.spec.*")
DOC_PATTERNS = ("README*", "CHANGELOG*", "docs/**", "**/*.md", "**/*.rst")
WORKFLOW_PATTERNS = (".github/workflows/**", ".gitlab-ci.yml", "Jenkinsfile")
CONFIG_PATTERNS = (
    ".steadfast/**", "pyproject.toml", "setup.cfg", "setup.py", "package.json",
    "Cargo.toml", "go.mod", "Dockerfile", "docker-compose.yml",
)
SECRET_PATTERNS = (
    ".env", ".env.*", "**/.env", "**/.env.*", "**/*credentials*",
    "**/*secret*", "**/*.pem", "**/*.key", "**/*.p12", "**/*.pfx",
)
PUBLIC_SURFACE_STEMS = {"cli", "contracts", "policy", "integrations", "pipeline", "__init__"}
MAX_PATHS = 10_000


def _matches(path: str, patterns: Iterable[str]) -> bool:
    return any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns)


def _classify(path: str) -> list[str]:
    kinds = []
    if _matches(path, SOURCE_PATTERNS):
        kinds.append("source")
    if _matches(path, TEST_PATTERNS):
        kinds.append("test")
    if _matches(path, DOC_PATTERNS):
        kinds.append("documentation")
    if _matches(path, WORKFLOW_PATTERNS):
        kinds.append("workflow")
    if _matches(path, CONFIG_PATTERNS):
        kinds.append("configuration")
    if _matches(path, SECRET_PATTERNS):
        kinds.append("sensitive-path")
    if not kinds:
        kinds.append("other")
    return kinds


def _git_numstat(repo: Path, base: str | None) -> dict[str, dict[str, int | None]]:
    """Return best-effort added/deleted line counts without invoking a shell."""
    commands: list[list[str]] = []
    if base:
        commands.append(["git", "diff", "--numstat", f"{base}...HEAD"])
        commands.append(["git", "diff", "--numstat", "HEAD"])
    else:
        commands.append(["git", "diff", "--numstat", "HEAD"])
    stats: dict[str, dict[str, int | None]] = {}
    for command in commands:
        try:
            result = subprocess.run(command, cwd=repo, capture_output=True, text=True,
                                    timeout=10, check=False)
        except (OSError, subprocess.TimeoutExpired):
            continue
        if result.returncode:
            continue
        for line in result.stdout.splitlines():
            parts = line.split("\t", 2)
            if len(parts) != 3:
                continue
            added = None if parts[0] == "-" else int(parts[0])
            deleted = None if parts[1] == "-" else int(parts[1])
            previous = stats.get(parts[2], {"added": 0, "deleted": 0})
            stats[parts[2]] = {
                "added": None if added is None or previous.get("added") is None else int(previous.get("added", 0)) + added,
                "deleted": None if deleted is None or previous.get("deleted") is None else int(previous.get("deleted", 0)) + deleted,
            }
    return stats


def _test_candidates(path: str) -> list[str]:
    normalized = path.replace("\\", "/")
    stem = Path(normalized).stem
    if stem.startswith("__") and stem.endswith("__"):
        stem = stem.strip("_")
    return [
        f"tests/test_{stem}.py",
        f"tests/{stem}_test.py",
        f"test/test_{stem}.py",
        f"tests/{stem}.spec.ts",
        f"tests/{stem}.test.ts",
    ]


def _risk(path_count: int, classifications: list[list[str]], findings: list[dict[str, Any]],
          stats: dict[str, dict[str, int | None]]) -> tuple[int, list[str]]:
    score = 0
    factors: list[str] = []
    if path_count > 20:
        score += 20
        factors.append("large change set: more than 20 paths")
    elif path_count > 8:
        score += 10
        factors.append("medium change set: more than 8 paths")
    flat = {kind for kinds in classifications for kind in kinds}
    if "workflow" in flat:
        score += 25
        factors.append("CI/workflow configuration changed")
    if "configuration" in flat:
        score += 15
        factors.append("project or governance configuration changed")
    if "sensitive-path" in flat:
        score += 50
        factors.append("sensitive-looking path changed")
    if "source" in flat and "test" not in flat:
        score += 15
        factors.append("source changed without a test file in the same change set")
    if "source" in flat and "documentation" not in flat:
        score += 5
        factors.append("source changed without documentation in the same change set")
    if any(item.get("severity") == "error" for item in findings):
        score += 30
        factors.append("impact analysis found blocking issues")
    deleted = sum(int(value.get("deleted") or 0) for value in stats.values())
    if deleted >= 500:
        score += 10
        factors.append("large deletion volume")
    return min(100, score), factors


def analyze_change_impact(
    repo: Path,
    *,
    base: str | None = None,
    paths: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Explain change surface, expected review gates and likely missing evidence.

    The analysis is heuristic: it never claims semantic dependency or test
    coverage. It reports observable path relationships and recommended review.
    """
    root = repo.resolve()
    findings: list[dict[str, Any]] = []
    if paths is None:
        if not is_repo(root):
            return {
                "schema_version": 1, "passed": False, "mode": "git",
                "changed_count": 0, "changed_files": [], "risk_score": 0,
                "risk_factors": [], "required_gates": [],
                "findings": [{"severity": "error", "code": "IMPACT_GIT_UNAVAILABLE",
                              "path": "", "message": "Change impact requires a Git worktree or explicit changed paths."}],
            }
        try:
            selected = changed_paths(root, base)
        except (GitError, OSError, ValueError) as exc:
            return {
                "schema_version": 1, "passed": False, "mode": "git",
                "changed_count": 0, "changed_files": [], "risk_score": 0,
                "risk_factors": [], "required_gates": [],
                "findings": [{"severity": "error", "code": "IMPACT_DIFF_FAILED",
                              "path": "", "message": str(exc)}],
            }
        mode = "git"
    else:
        selected = sorted(set(str(item) for item in paths))
        mode = "explicit"
    if len(selected) > MAX_PATHS:
        raise ValueError(f"impact analysis is limited to {MAX_PATHS} changed paths")
    safe_paths: list[str] = []
    for raw in selected:
        candidate = Path(raw)
        if not raw or candidate.is_absolute() or ".." in candidate.parts:
            findings.append({"severity": "error", "code": "IMPACT_PATH_INVALID",
                             "path": raw, "message": "Changed path must be repository-relative and cannot traverse parents."})
            continue
        safe_paths.append(candidate.as_posix())
    selected = sorted(set(safe_paths))
    stats = _git_numstat(root, base) if mode == "git" else {}
    changed = []
    all_kinds: set[str] = set()
    for path in selected:
        kinds = _classify(path)
        all_kinds.update(kinds)
        stat = stats.get(path, {})
        absolute = root / path
        current_lines = None
        if absolute.is_file() and not absolute.is_symlink():
            try:
                current_lines = len(absolute.read_text(encoding="utf-8").splitlines())
            except (OSError, UnicodeError):
                current_lines = None
        changed.append({
            "path": path,
            "kinds": kinds,
            "added_lines": stat.get("added"),
            "deleted_lines": stat.get("deleted"),
            "current_lines": current_lines,
            "exists": absolute.exists(),
        })
        if "sensitive-path" in kinds:
            findings.append({"severity": "error", "code": "IMPACT_SENSITIVE_PATH",
                             "path": path, "message": "A credential- or secret-looking path changed; review for accidental secret exposure."})
    source_files = [item["path"] for item in changed if "source" in item["kinds"]]
    test_files = [item["path"] for item in changed if "test" in item["kinds"]]
    docs_files = [item["path"] for item in changed if "documentation" in item["kinds"]]
    missing_test_links = []
    for source in source_files:
        candidates = _test_candidates(source)
        present = next((candidate for candidate in candidates if candidate in test_files), None)
        if not present:
            # Existing neighboring tests are useful context but do not count as
            # changed regression coverage for this change set.
            existing = [candidate for candidate in candidates if (root / candidate).is_file()]
            missing_test_links.append({"source": source, "expected_candidates": candidates,
                                       "existing_candidates": existing})
            findings.append({"severity": "warning", "code": "IMPACT_SOURCE_WITHOUT_CHANGED_TEST",
                             "path": source, "message": "No conventional matching test file changed with this source file."})
    public_source = [path for path in source_files if Path(path).stem in PUBLIC_SURFACE_STEMS]
    if public_source and not docs_files:
        findings.append({"severity": "warning", "code": "IMPACT_PUBLIC_API_WITHOUT_DOCS",
                         "path": ", ".join(public_source[:5]),
                         "message": "Public CLI, policy, integration or contract code changed without a documentation file in this change set."})
    required_gates = ["unit-tests", "scope-check"]
    if "workflow" in all_kinds or "configuration" in all_kinds:
        required_gates.extend(["security-check", "audit"])
    if public_source:
        required_gates.append("docs-check")
    if "sensitive-path" in all_kinds:
        required_gates.extend(["secret-scan", "human-review"])
    if "source" in all_kinds:
        required_gates.append("regression-review")
    required_gates = list(dict.fromkeys(required_gates))
    score, factors = _risk(len(selected), [item["kinds"] for item in changed], findings, stats)
    return {
        "schema_version": 1,
        "mode": mode,
        "base": base or "",
        "passed": not any(item.get("severity") == "error" for item in findings),
        "changed_count": len(changed),
        "changed_files": changed,
        "classification_counts": {kind: sum(kind in item["kinds"] for item in changed)
                                  for kind in sorted(all_kinds)},
        "source_files": source_files,
        "test_files": test_files,
        "documentation_files": docs_files,
        "missing_test_links": missing_test_links,
        "risk_score": score,
        "risk_factors": factors,
        "required_gates": required_gates,
        "findings": findings,
        "limitations": [
            "Path-based heuristics cannot prove semantic dependencies or actual test coverage.",
            "A matching test path is evidence of a changed test file, not proof that the test asserts the changed behavior.",
            "The risk score prioritizes human review; it is not a probability of defects.",
        ],
    }
