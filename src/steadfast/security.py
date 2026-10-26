from __future__ import annotations

import fnmatch
import re
from pathlib import Path
from typing import Any, Iterable



SECRET_ASSIGNMENT = re.compile(
    r"""(?i)\b(api[_-]?key|client[_-]?secret|password|access[_-]?token)\s*[:=]\s*(['"])([^'"]{12,})\2"""
)
AWS_ACCESS_KEY = re.compile(r"\bAKIA[0-9A-Z]{16}\b")
PRIVATE_KEY_MARKER = "-----BEGIN " + "PRIVATE KEY-----"
RISKY_API_PATTERNS = (
    (re.compile(r"\btempfile\.mktemp\s*\("), "INSECURE_TEMPFILE", "tempfile.mktemp can race with another process; use a securely created temporary file."),
    (re.compile(r"\bos\.system\s*\("), "OS_SYSTEM_CALL", "os.system invokes a command shell; prefer argument-array subprocess APIs."),
    (re.compile(r"\b(?:hashlib\.)?md5\s*\("), "WEAK_HASH_MD5", "MD5 is unsuitable for security-sensitive integrity or password hashing."),
    (re.compile(r"\b(?:hashlib\.)?sha1\s*\("), "WEAK_HASH_SHA1", "SHA-1 is unsuitable for collision-resistant security decisions."),
    (re.compile(r"\bverify\s*=\s*False\b"), "TLS_VERIFY_DISABLED", "TLS certificate verification is disabled."),
    (re.compile(r"\byaml\.load\s*\("), "YAML_LOAD_REVIEW", "yaml.load can construct unsafe objects unless a safe loader is explicitly used."),
    (re.compile(r"\bpickle\.(?:load|loads)\s*\("), "UNTRUSTED_PICKLE_REVIEW", "Pickle deserialization can execute code; never load untrusted data."),
)
UNSAFE_EXEC_PATTERNS = (
    (re.compile(r"\beval\s*\("), "DYNAMIC_EVAL", "Dynamic eval call needs a security review."),
    (re.compile(r"\bexec\s*\("), "DYNAMIC_EXEC", "Dynamic exec call needs a security review."),
    (re.compile(r"\bshell\s*=\s*True\b"), "SHELL_TRUE", "Shell-based subprocess execution needs input validation."),
)
PLACEHOLDERS = {"changeme", "change-me", "example", "placeholder", "your-key-here", "none", "null"}


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return None


def _source_files(repo: Path, policy: dict[str, Any]) -> Iterable[Path]:
    ignored = policy.get("ignored_paths", [])
    roots = policy.get("security_scan_paths", policy.get("implementation_paths", ["src/**"]))
    for path in sorted(repo.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        relative = path.relative_to(repo).as_posix()
        if _matches(relative, ignored) or not _matches(relative, roots):
            continue
        if path.suffix.lower() not in {".py", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".go", ".rs", ".java", ".c", ".h", ".cpp", ".hpp", ".cuk", ".sh", ".yaml", ".yml", ".toml", ".json"}:
            continue
        yield path


def security_findings(repo: Path, policy: dict[str, Any]) -> list[dict[str, str]]:
    """Run conservative local pattern checks; findings require human review."""
    findings: list[dict[str, str]] = []
    for path in _source_files(repo, policy):
        relative = path.relative_to(repo).as_posix()
        text = _read_text(path)
        if text is None:
            continue
        if path.name == ".env" or (path.name.startswith(".env.") and path.name not in {".env.example", ".env.sample"}):
            findings.append({
                "severity": "error", "code": "ENV_FILE_IN_SOURCE_SCOPE",
                "path": relative, "message": "Environment files may contain secrets; keep them out of implementation scope.",
            })
        for line_number, line in enumerate(text.splitlines(), start=1):
            if PRIVATE_KEY_MARKER in line:
                findings.append({
                    "severity": "error", "code": "PRIVATE_KEY_MATERIAL",
                    "path": relative, "message": f"Private-key marker found at line {line_number}; value is not copied into the report.",
                })
            if AWS_ACCESS_KEY.search(line):
                findings.append({
                    "severity": "error", "code": "AWS_ACCESS_KEY_PATTERN",
                    "path": relative, "message": f"Possible AWS access-key identifier at line {line_number}.",
                })
            for match in SECRET_ASSIGNMENT.finditer(line):
                value = match.group(3).strip()
                if value.lower() not in PLACEHOLDERS and not value.lower().startswith(("your_", "example_", "test_")):
                    findings.append({
                        "severity": "error", "code": "POSSIBLE_HARDCODED_SECRET",
                        "path": relative,
                        "message": f"Possible hardcoded {match.group(1)} at line {line_number}; secret value redacted.",
                    })
            for pattern, code, message in (*UNSAFE_EXEC_PATTERNS, *RISKY_API_PATTERNS):
                if pattern.search(line):
                    findings.append({
                        "severity": "warning", "code": code, "path": relative,
                        "message": f"{message} (line {line_number})",
                    })
    return findings


def workflow_findings(repo: Path) -> list[dict[str, str]]:
    """Check common workflow trust-boundary hazards without executing workflows."""
    directory = repo / ".github" / "workflows"
    if not directory.is_dir():
        return []
    findings: list[dict[str, str]] = []
    for path in sorted(directory.glob("*.y*ml")):
        text = _read_text(path)
        if text is None:
            continue
        rel = path.relative_to(repo).as_posix()
        if "pull_request_target:" in text and re.search(r"(?m)^\s*-\s*uses:\s*actions/checkout@", text):
            findings.append({
                "severity": "error", "code": "PR_TARGET_CHECKOUT_RISK",
                "path": rel,
                "message": "pull_request_target combined with checkout can expose write-context secrets to untrusted code.",
            })
        if re.search(r"(?m)^\s*permissions:\s*\n\s+contents:\s*write", text):
            findings.append({
                "severity": "warning", "code": "WORKFLOW_WRITE_PERMISSION",
                "path": rel,
                "message": "Workflow grants contents: write; verify that write permission is essential.",
            })
        for line_number, line in enumerate(text.splitlines(), start=1):
            if re.search(r"(?m)^\s*(?:-\s*)?run:\s*.*\$\{\{\s*github\.event\.(?:issue|pull_request|comment|review|review_comment)\.", line):
                findings.append({
                    "severity": "error", "code": "UNTRUSTED_EVENT_SHELL_INTERPOLATION",
                    "path": rel,
                    "message": f"Untrusted GitHub event data is interpolated directly into a shell command at line {line_number}; pass it through an environment variable and quote it.",
                })
            if re.search(r"(?m)\buses:\s*[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+@v\d+", line):
                findings.append({
                    "severity": "warning", "code": "ACTION_TAG_NOT_PINNED",
                    "path": rel,
                    "message": f"Action uses a movable version tag at line {line_number}; pin a reviewed full commit SHA for stronger supply-chain integrity.",
                })
    return findings


def _matches(path: str, patterns: list[str]) -> bool:
    return any(
        fnmatch.fnmatchcase(path, pattern)
        or (pattern.endswith("/**") and path.startswith(pattern[:-2]))
        for pattern in patterns
    )
