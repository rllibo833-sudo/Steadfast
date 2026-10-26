from __future__ import annotations

import ast
import hashlib
import os
import re
from pathlib import Path
from typing import Any

from .checks import matches, product_code_lines
from .policy import load_policy

DOC_SUFFIXES = {".md", ".mdc", ".rst", ".txt"}
EXAMPLE_RE = re.compile(r"(?m)^\s*(?:\$\s*)?steadfast\s+([^\n#]+)")
SKIP = {".git", ".venv", "venv", "node_modules", "__pycache__", "dist", "build", ".pytest_cache"}


def _files(root: Path, suffixes: set[str]) -> list[Path]:
    result = []
    for current, dirs, names in os.walk(root, followlinks=False):
        dirs[:] = [name for name in dirs if name not in SKIP and not (Path(current) / name).is_symlink()]
        for name in names:
            path = Path(current) / name
            if not path.is_symlink() and path.suffix.lower() in suffixes:
                result.append(path)
    return sorted(result)


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _source_facts(repo: Path, policy: dict[str, Any]) -> dict[str, Any]:
    source_files, tests, modules = [], [], []
    for path in _files(repo, {".py"}):
        rel = path.relative_to(repo).as_posix()
        if matches(rel, policy.get("ignored_paths", [])):
            continue
        if rel.startswith("src/"):
            source_files.append(path)
            modules.append(rel)
        elif rel.startswith("tests/"):
            tests.append(path)
    code_lines, code_paths = product_code_lines(repo, policy)
    test_lines = 0
    for path in tests:
        try:
            test_lines += sum(1 for line in path.read_text(encoding="utf-8").splitlines()
                              if line.strip() and not line.lstrip().startswith("#"))
        except (OSError, UnicodeError):
            continue
    return {
        "implementation": {"files": len(source_files), "nonblank_noncomment_lines": code_lines,
                           "paths": sorted(code_paths)},
        "tests": {"files": len(tests), "nonblank_noncomment_lines": test_lines,
                  "implementation_to_test_line_ratio": round(code_lines / test_lines, 2) if test_lines else None},
        "python_modules": sorted(modules),
    }


def _cli_commands(repo: Path) -> tuple[list[str], dict[str, list[str]], list[dict[str, str]]]:
    path = repo / "src" / "steadfast" / "cli.py"
    try:
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, UnicodeError, SyntaxError) as exc:
        return [], {}, [{"severity": "error", "code": "CODE_TRUTH_CLI_UNREADABLE",
                         "path": "src/steadfast/cli.py", "message": str(exc)}]
    try:
        # The instantiated argparse tree, not a Markdown list, defines available commands.
        from .cli import parser
        root_parser = parser()
        action = next(a for a in root_parser._actions if hasattr(a, "choices") and isinstance(a.choices, dict))
        commands = sorted(action.choices)
        nested: dict[str, list[str]] = {}
        for name, command_parser in action.choices.items():
            child = next((a for a in command_parser._actions
                          if hasattr(a, "choices") and isinstance(a.choices, dict)), None)
            nested[name] = sorted(child.choices) if child else []
        return commands, nested, []
    except (ImportError, StopIteration, AttributeError, TypeError, ValueError) as exc:
        return [], {}, [{"severity": "error", "code": "CODE_TRUTH_RUNTIME_PARSER_FAILED",
                         "path": "src/steadfast/cli.py", "message": str(exc)}]


def _example_findings(repo: Path, commands: list[str], nested: dict[str, list[str]]) -> tuple[list[dict[str, str]], int]:
    findings: list[dict[str, str]] = []
    count = 0
    for path in _files(repo, DOC_SUFFIXES):
        rel = path.relative_to(repo).as_posix()
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        for match in EXAMPLE_RE.finditer(content):
            count += 1
            tokens = re.split(r"\s+", match.group(1).strip())
            # Skip global options and their single values without executing anything.
            while tokens and tokens[0].startswith("-"):
                flag = tokens.pop(0)
                if flag in {"--repo", "--format", "--port", "--host", "--manifest", "--workers",
                            "--record", "--history", "--limit", "--status", "--state", "--priority",
                            "--query", "--goal", "--title", "--note", "--agent"} and tokens:
                    tokens.pop(0)
            if not tokens:
                continue
            top = tokens[0]
            if top not in commands:
                findings.append({"severity": "error", "code": "DOC_COMMAND_NOT_IN_CODE",
                                 "path": rel, "message": f"Documented command 'steadfast {top}' is not a runtime CLI command."})
                continue
            children = nested.get(top, [])
            if len(tokens) > 1 and children and not tokens[1].startswith("-") and tokens[1] not in children:
                findings.append({"severity": "error", "code": "DOC_SUBCOMMAND_NOT_IN_CODE",
                                 "path": rel, "message": f"Documented subcommand 'steadfast {top} {tokens[1]}' is not available in runtime parser."})
    return findings, count


def code_truth_report(repo: Path) -> dict[str, Any]:
    """Derive product facts from implementation and detect docs that contradict the runtime CLI."""
    repo = repo.resolve()
    policy = load_policy(repo)
    commands, nested, findings = _cli_commands(repo)
    example_findings, examples_checked = _example_findings(repo, commands, nested)
    findings.extend(example_findings)
    facts = _source_facts(repo, policy)
    project_path = repo / "pyproject.toml"
    try:
        project = project_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        project = ""
        findings.append({"severity": "error", "code": "CODE_TRUTH_PROJECT_CONFIG_MISSING",
                         "path": "pyproject.toml", "message": str(exc)})
    entrypoint = 'steadfast = "steadfast.cli:main"' in project
    if not entrypoint:
        findings.append({"severity": "error", "code": "CODE_TRUTH_ENTRYPOINT_DRIFT",
                         "path": "pyproject.toml", "message": "Console entrypoint does not target steadfast.cli:main."})
    module_entry = repo / "src" / "steadfast" / "__main__.py"
    if not module_entry.is_file():
        findings.append({"severity": "error", "code": "CODE_TRUTH_MODULE_ENTRY_MISSING",
                         "path": "src/steadfast/__main__.py", "message": "python -m steadfast entrypoint is missing."})
    source_hashes = {}
    for rel in facts["implementation"]["paths"]:
        try:
            source_hashes[rel] = _sha(repo / rel)
        except OSError:
            source_hashes[rel] = None
    errors = sum(item["severity"] == "error" for item in findings)
    return {
        "tool": "steadfast", "truth_model": "implementation-first",
        "source_of_truth": ["runtime argparse parser", "src/steadfast/**/*.py", "pyproject.toml",
                            ".steadfast/pipeline.json", "tests/**/*.py"],
        "product_facts": facts,
        "runtime_cli": {"commands": commands, "subcommands": nested, "examples_checked": examples_checked},
        "entrypoints": {"console_script_valid": entrypoint, "module_entrypoint_exists": module_entry.is_file()},
        "source_sha256": source_hashes,
        "findings": findings,
        "summary": {"errors": errors, "warnings": sum(x["severity"] == "warning" for x in findings)},
        "passed": errors == 0,
    }
