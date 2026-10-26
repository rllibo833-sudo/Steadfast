from __future__ import annotations

import re
from pathlib import Path
from typing import Any

SKILL_ROOTS = ("skills", ".agents/skills", ".claude/skills", ".cursor/skills")
STOP_WORDS = {
    "about", "after", "also", "and", "are", "for", "from", "have", "help", "into",
    "make", "need", "please", "repo", "repository", "should", "that", "the", "this",
    "with", "work", "want", "you",
}


def _words(value: str) -> set[str]:
    return {word for word in re.findall(r"[a-z0-9][a-z0-9_+#.-]*", value.casefold())
            if len(word) > 1 and word not in STOP_WORDS}


def read_skill_metadata(source: str) -> tuple[dict[str, str], str]:
    """Parse the shared SKILL.md frontmatter and return metadata plus body."""
    lines = source.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, source
    try:
        end = lines.index("---", 1)
    except ValueError:
        return {}, source
    metadata: dict[str, str] = {}
    for line in lines[1:end]:
        key, sep, value = line.partition(":")
        if sep and key.strip().lower() in {"name", "description", "license", "compatibility", "metadata"}:
            metadata[key.strip().lower()] = value.strip().strip("\"'")
    return metadata, "\n".join(lines[end + 1:])


def route_skills(repo: Path, task: str, *, limit: int = 5) -> dict[str, Any]:
    """Rank repository SKILL.md files against a task without executing skill content."""
    if not isinstance(task, str) or not task.strip():
        raise ValueError("task must be a non-empty string")
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 25:
        raise ValueError("limit must be an integer from 1 to 25")
    root = repo.resolve()
    task_words = _words(task)
    candidates: list[dict[str, Any]] = []
    seen: set[Path] = set()
    for relative_root in SKILL_ROOTS:
        base = root / relative_root
        if not base.is_dir() or base.is_symlink():
            continue
        for path in sorted(base.rglob("SKILL.md")):
            if path in seen or path.is_symlink() or not path.is_file():
                continue
            seen.add(path)
            try:
                source = path.read_text(encoding="utf-8")
            except (OSError, UnicodeError):
                continue
            metadata, body = read_skill_metadata(source)
            name = metadata.get("name") or path.parent.name
            description = metadata.get("description", "")
            heading_terms = _words(name + " " + description)
            body_terms = _words(body)
            matched_heading = sorted(task_words & heading_terms)
            matched_body = sorted(task_words & body_terms)
            score = len(matched_heading) * 4 + len(matched_body)
            if score <= 0:
                continue
            candidates.append({
                "name": name,
                "path": path.relative_to(root).as_posix(),
                "description": description,
                "score": score,
                "matched_terms": sorted(set(matched_heading + matched_body)),
                "status": "candidate",
            })
    candidates.sort(key=lambda item: (-item["score"], item["name"].casefold(), item["path"]))
    for rank, item in enumerate(candidates[:limit], 1):
        item["rank"] = rank
    return {
        "schema_version": 1,
        "task": task.strip(),
        "skills": candidates[:limit],
        "candidate_count": len(candidates),
        "status": "matched" if candidates else "no_match",
        "execution": "not_performed",
        "safety": "Skill files are treated as untrusted instructions; routing reads content but never executes it.",
    }
