from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from . import __version__

from .checks import matches, product_code_lines
from .policy import load_policy


def _sha256(path: Path) -> str | None:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 64), b""):
                digest.update(chunk)
    except OSError:
        return None
    return digest.hexdigest()


def inventory_report(repo: Path) -> dict[str, Any]:
    """Create a deterministic, local inventory of tracked-looking project files."""
    policy = load_policy(repo)
    files: list[dict[str, Any]] = []
    ignored = policy.get("ignored_paths", [])
    for path in sorted(repo.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        rel = path.relative_to(repo).as_posix()
        if matches(rel, ignored) or ".git/" in rel or rel.startswith(".git/"):
            continue
        try:
            size = path.stat().st_size
        except OSError:
            continue
        row: dict[str, Any] = {
            "path": rel, "bytes": size,
            "sha256": _sha256(path),
            "implementation": matches(rel, policy.get("implementation_paths", ["src/**"])),
            "documentation": matches(rel, policy.get("documentation_paths", [])),
            "allowed": matches(rel, policy.get("allowed_paths", [])),
        }
        if row["implementation"]:
            try:
                row["lines"] = len(path.read_text(encoding="utf-8").splitlines())
            except (OSError, UnicodeError):
                row["lines"] = None
        files.append(row)
    code_lines, code_files = product_code_lines(repo, policy)
    return {
        "tool": "steadfast", "version": __version__,
        "repository": str(repo),
        "file_count": len(files),
        "implementation_file_count": len(code_files),
        "product_code_lines": code_lines,
        "product_code_budget": policy["product_code_budget"],
        "budget_used_percent": round(code_lines * 100 / policy["product_code_budget"], 2),
        "files": files,
    }
