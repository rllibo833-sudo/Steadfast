from __future__ import annotations
import json
from pathlib import Path
from typing import Any

DEFAULT_POLICY: dict[str, Any] = {
    "version": 1,
    "product_code_budget": 20000,
    "allowed_paths": ["src/**", "tests/**", "skills/**", ".github/workflows/**", ".steadfast/**", "README.md", "LICENSE", "pyproject.toml", "agents/**", "kits/**"],
    "agent_path_rules": {"code": ["src/**", "tests/**", "skills/**", "docs/**", "evidence/**", "CHANGELOG.md", "README.md", "AGENTS.md", "agents/**", "kits/**", "pyproject.toml"], "media": ["assets/**", "media/**", "images/**", "videos/**", "audio/**", "public/assets/**", "public/images/**", "public/videos/**", "public/audio/**"]},
    "agent_protected_paths": [".steadfast/**", ".github/workflows/**", ".codex/**"],
    "documentation_paths": ["README.md", "docs/**", "CHANGELOG.md", "ROADMAP.md", "ARCHITECTURE.md", "SPEC.md"],
    "required_evidence": ["evidence/verification.md"],
    "implementation_paths": ["src/**"],
    "ignored_paths": [".git/**", ".venv/**", "build/**", "dist/**", "__pycache__/**"],
    "max_active_goals": 3,
    "forbidden_roadmap_phrases": ["someday", "maybe later", "future ideas"]
}

DEFAULT_GOAL = "# Product goal\n\n## Outcome\nState the single user-visible outcome this project is delivering.\n\n## Non-goals\n- List explicitly excluded work.\n\n## Acceptance criteria\n- [ ] Observable behavior\n- [ ] Verification command and expected result\n\n## Scope change process\nAny new capability must be proposed separately and approved by a maintainer before implementation.\n"

def policy_path(repo: Path) -> Path:
    return repo / ".steadfast" / "policy.json"

def load_policy(repo: Path) -> dict[str, Any]:
    path = policy_path(repo)
    directory = repo / ".steadfast"
    if directory.is_symlink() or path.is_symlink():
        raise ValueError("Steadfast policy paths may not traverse symlinks.")
    if not path.exists():
        raise FileNotFoundError("Missing .steadfast/policy.json; run `steadfast init`.")
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("version") != 1:
        raise ValueError("Unsupported policy version; expected version 1.")
    if not isinstance(data.get("allowed_paths"), list):
        raise ValueError("Policy field allowed_paths must be a list.")
    if not isinstance(data.get("product_code_budget"), int) or data["product_code_budget"] < 1:
        raise ValueError("Policy field product_code_budget must be a positive integer.")
    return data

def init_policy(repo: Path) -> list[str]:
    directory = repo / ".steadfast"
    if directory.is_symlink():
        raise ValueError("Steadfast policy directory may not be a symlink.")
    directory.mkdir(parents=True, exist_ok=True)
    created = []
    p = policy_path(repo)
    if not p.exists():
        p.write_text(json.dumps(DEFAULT_POLICY, indent=2) + "\n", encoding="utf-8")
        created.append(str(p.relative_to(repo)))
    goal = directory / "goal.md"
    if not goal.exists():
        goal.write_text(DEFAULT_GOAL, encoding="utf-8")
        created.append(str(goal.relative_to(repo)))
    evidence = repo / "evidence" / "verification.md"
    if not evidence.exists():
        evidence.parent.mkdir(parents=True, exist_ok=True)
        evidence.write_text("# Verification evidence\n\nRecord exact commands, exit codes, and meaningful results here.\n", encoding="utf-8")
        created.append(str(evidence.relative_to(repo)))
    return created
