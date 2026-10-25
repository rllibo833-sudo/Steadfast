from __future__ import annotations
import fnmatch, json
from pathlib import Path
from typing import Any
from .gitops import changed_paths, is_repo
from .policy import load_policy

def matches(path: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatchcase(path, p) or (p.endswith("/**") and path.startswith(p[:-3])) for p in patterns)

def product_code_lines(repo: Path, policy: dict[str, Any]) -> tuple[int, list[str]]:
    files, total = [], 0
    for path in repo.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(repo).as_posix()
        if not matches(rel, policy.get("implementation_paths", ["src/**"])) or matches(rel, policy.get("ignored_paths", [])):
            continue
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeError):
            continue
        total += sum(1 for line in lines if line.strip() and not line.lstrip().startswith("#"))
        files.append(rel)
    return total, files

def scope_findings(repo: Path, policy: dict[str, Any], paths: list[str] | None = None) -> list[dict[str, str]]:
    findings = []
    for path in paths if paths is not None else changed_paths(repo):
        if not matches(path, policy.get("allowed_paths", [])) and not matches(path, policy.get("ignored_paths", [])):
            findings.append({"severity":"error","code":"SCOPE_OUTSIDE_ALLOWLIST","path":path,"message":"Changed path is outside the configured allowlist."})
    return findings

def evidence_findings(repo: Path, policy: dict[str, Any]) -> list[dict[str, str]]:
    out = []
    for item in policy.get("required_evidence", []):
        p = repo / item
        if not p.is_file() or len(p.read_text(encoding="utf-8").strip()) < 40:
            out.append({"severity":"error","code":"EVIDENCE_MISSING","path":item,"message":"Required verification evidence is missing or too short."})
    return out

def run_audit(repo: Path, base: str | None = None) -> dict[str, Any]:
    policy = load_policy(repo)
    paths = changed_paths(repo, base) if is_repo(repo) else []
    count, files = product_code_lines(repo, policy)
    findings = scope_findings(repo, policy, paths) + evidence_findings(repo, policy)
    if count > policy["product_code_budget"]:
        findings.append({"severity":"error","code":"PRODUCT_CODE_BUDGET_EXCEEDED","path":"src","message":f"{count} counted lines exceed the {policy['product_code_budget']} line budget."})
    if any(p.startswith("src/") for p in paths) and not any(p.startswith(("README", "docs/", "CHANGELOG")) for p in paths):
        findings.append({"severity":"warning","code":"DOCS_NOT_CHANGED","path":"src","message":"Implementation changed; confirm related documentation remains accurate."})
    return {"tool":"steadfast","version":"0.1.0","repository":str(repo),"changed_paths":paths,"product_code_lines":count,"product_code_budget":policy["product_code_budget"],"counted_code_files":len(files),"findings":findings,"summary":{"errors":sum(x["severity"]=="error" for x in findings),"warnings":sum(x["severity"]=="warning" for x in findings),"info":sum(x["severity"]=="info" for x in findings)},"passed":not any(x["severity"]=="error" for x in findings)}
