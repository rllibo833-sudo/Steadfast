from __future__ import annotations

import re
from pathlib import Path
from typing import Any


def cli_commands(cli_source: str) -> list[str]:
    """Extract command names from argparse add_parser declarations."""
    return sorted(set(re.findall(r'commands?\.add_parser\(\s*["\']([a-z][a-z0-9-]*)["\']', cli_source)))


def documentation_sync_findings(repo: Path, cli_path: Path | None = None) -> list[dict[str, str]]:
    cli_file = cli_path or repo / "src" / "steadfast" / "cli.py"
    readme = repo / "README.md"
    try:
        source = cli_file.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        try:
            rel = cli_file.relative_to(repo).as_posix()
        except ValueError:
            rel = str(cli_file)
        return [{
            "severity": "error", "code": "CLI_SOURCE_UNREADABLE",
            "path": rel, "message": f"Cannot inspect CLI command declarations: {exc}",
        }]
    try:
        docs = readme.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        return [{
            "severity": "error", "code": "README_UNREADABLE",
            "path": "README.md", "message": f"Cannot read README: {exc}",
        }]
    findings = []
    for command in cli_commands(source):
        if f"steadfast {command}" not in docs and f"`{command}`" not in docs:
            findings.append({
                "severity": "warning", "code": "CLI_DOCS_MISSING_COMMAND",
                "path": "README.md",
                "message": f"CLI command {command!r} is not documented in README.md.",
            })
    project = repo / "pyproject.toml"
    try:
        config = project.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        config = ""
    if 'steadfast = "steadfast.cli:main"' not in config:
        findings.append({
            "severity": "error", "code": "CLI_ENTRYPOINT_MISSING",
            "path": "pyproject.toml",
            "message": "The console script entry point does not target steadfast.cli:main.",
        })
    if not (repo / "src" / "steadfast" / "__main__.py").is_file():
        findings.append({
            "severity": "error", "code": "MODULE_ENTRYPOINT_MISSING",
            "path": "src/steadfast/__main__.py",
            "message": "python -m steadfast requires src/steadfast/__main__.py.",
        })
    return findings


def docs_sync_report(repo: Path) -> dict[str, Any]:
    findings = documentation_sync_findings(repo)
    return {
        "tool": "steadfast", "check": "documentation-sync",
        "repository": str(repo), "findings": findings,
        "summary": {
            "errors": sum(item["severity"] == "error" for item in findings),
            "warnings": sum(item["severity"] == "warning" for item in findings),
        },
        "passed": not any(item["severity"] == "error" for item in findings),
    }
