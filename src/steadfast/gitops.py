from __future__ import annotations
import subprocess
from pathlib import Path

class GitError(RuntimeError):
    pass

def git(repo: Path, *args: str, check: bool = True) -> str:
    proc = subprocess.run(["git", *args], cwd=repo, text=True, capture_output=True)
    if check and proc.returncode:
        raise GitError(proc.stderr.strip() or proc.stdout.strip() or "Git command failed")
    return proc.stdout.strip()

def is_repo(repo: Path) -> bool:
    return subprocess.run(["git", "rev-parse", "--is-inside-work-tree"], cwd=repo,
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0

def changed_paths(repo: Path, base: str | None = None) -> list[str]:
    if base:
        output = git(repo, "diff", "--name-only", "--diff-filter=ACDMRTUXB", f"{base}...HEAD")
        working = git(repo, "status", "--porcelain", "--untracked-files=all")
    else:
        output = git(repo, "diff", "--name-only", "--diff-filter=ACDMRTUXB", "HEAD")
        working = git(repo, "status", "--porcelain", "--untracked-files=all")
    paths = set(p for p in output.splitlines() if p)
    for line in working.splitlines():
        if len(line) > 3:
            paths.add(line[3:].split(" -> ")[-1])
    return sorted(paths)

def untracked_paths(repo: Path) -> list[str]:
    output = git(repo, "ls-files", "--others", "--exclude-standard")
    return [x for x in output.splitlines() if x]
