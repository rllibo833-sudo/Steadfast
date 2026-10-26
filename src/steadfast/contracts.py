from __future__ import annotations

import json
from pathlib import Path
from typing import Any

POLICY_REQUIRED_TYPES: dict[str, type] = {
    "version": int,
    "product_code_budget": int,
    "allowed_paths": list,
    "documentation_paths": list,
    "required_evidence": list,
    "implementation_paths": list,
    "ignored_paths": list,
}


def validate_policy_data(data: Any) -> list[dict[str, str]]:
    """Validate policy structure without reading or mutating repository files."""
    findings: list[dict[str, str]] = []
    if not isinstance(data, dict):
        return [{
            "severity": "error", "code": "POLICY_NOT_OBJECT",
            "path": ".steadfast/policy.json",
            "message": "Policy root must be a JSON object.",
        }]
    for key, expected in POLICY_REQUIRED_TYPES.items():
        if key not in data:
            findings.append({
                "severity": "error", "code": "POLICY_FIELD_MISSING",
                "path": f".steadfast/policy.json:{key}",
                "message": f"Required policy field {key!r} is missing.",
            })
            continue
        value = data[key]
        # bool is a subclass of int but is not a meaningful version/budget.
        if expected is int and (not isinstance(value, int) or isinstance(value, bool)):
            valid = False
        else:
            valid = isinstance(value, expected)
        if not valid:
            findings.append({
                "severity": "error", "code": "POLICY_FIELD_TYPE",
                "path": f".steadfast/policy.json:{key}",
                "message": f"Policy field {key!r} must be {expected.__name__}.",
            })
    if isinstance(data.get("version"), int) and data["version"] != 1:
        findings.append({
            "severity": "error", "code": "POLICY_VERSION_UNSUPPORTED",
            "path": ".steadfast/policy.json:version",
            "message": "Only policy version 1 is supported.",
        })
    if isinstance(data.get("product_code_budget"), int):
        if isinstance(data["product_code_budget"], bool) or data["product_code_budget"] < 1:
            findings.append({
                "severity": "error", "code": "POLICY_BUDGET_INVALID",
                "path": ".steadfast/policy.json:product_code_budget",
                "message": "Product code budget must be a positive integer.",
            })
    for key in ("allowed_paths", "documentation_paths", "required_evidence",
                "implementation_paths", "ignored_paths"):
        values = data.get(key)
        if isinstance(values, list):
            for index, item in enumerate(values):
                if not isinstance(item, str) or not item.strip():
                    findings.append({
                        "severity": "error", "code": "POLICY_PATTERN_INVALID",
                        "path": f".steadfast/policy.json:{key}[{index}]",
                        "message": "Policy entries must be non-empty strings.",
                    })
                elif key == "required_evidence":
                    candidate = Path(item)
                    if candidate.is_absolute() or ".." in candidate.parts:
                        findings.append({
                            "severity": "error", "code": "POLICY_EVIDENCE_PATH_UNSAFE",
                            "path": f".steadfast/policy.json:{key}[{index}]",
                            "message": "Evidence paths must remain inside the repository.",
                        })
    if isinstance(data.get("max_active_goals"), int) and data["max_active_goals"] < 1:
        findings.append({
            "severity": "error", "code": "POLICY_GOAL_LIMIT_INVALID",
            "path": ".steadfast/policy.json:max_active_goals",
            "message": "max_active_goals must be at least 1.",
        })
    return findings


def validate_policy_file(repo: Path) -> list[dict[str, str]]:
    path = repo / ".steadfast" / "policy.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return [{
            "severity": "error", "code": "POLICY_MISSING",
            "path": ".steadfast/policy.json",
            "message": "Policy file is missing; run steadfast init.",
        }]
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return [{
            "severity": "error", "code": "POLICY_UNREADABLE",
            "path": ".steadfast/policy.json",
            "message": f"Policy file cannot be read as valid UTF-8 JSON: {exc}",
        }]
    return validate_policy_data(data)


def contract_findings(repo: Path, policy: dict[str, Any]) -> list[dict[str, str]]:
    """Check simple, deterministic repository contracts configured by policy."""
    findings: list[dict[str, str]] = []
    for rel in policy.get("required_files", []):
        candidate = Path(rel)
        if candidate.is_absolute() or ".." in candidate.parts:
            findings.append({
                "severity": "error", "code": "CONTRACT_PATH_UNSAFE",
                "path": rel, "message": "Required file path must stay inside the repository.",
            })
            continue
        if not (repo / candidate).is_file():
            findings.append({
                "severity": "error", "code": "REQUIRED_FILE_MISSING",
                "path": rel, "message": "A policy-required repository file is missing.",
            })
    for rule in policy.get("required_text", []):
        if not isinstance(rule, dict):
            findings.append({
                "severity": "error", "code": "CONTRACT_RULE_INVALID",
                "path": ".steadfast/policy.json:required_text",
                "message": "Each required_text rule must be an object.",
            })
            continue
        rel, phrase = rule.get("path"), rule.get("contains")
        if not isinstance(rel, str) or not isinstance(phrase, str) or not phrase:
            findings.append({
                "severity": "error", "code": "CONTRACT_RULE_INVALID",
                "path": ".steadfast/policy.json:required_text",
                "message": "Each required_text rule needs non-empty path and contains values.",
            })
            continue
        candidate = Path(rel)
        if candidate.is_absolute() or ".." in candidate.parts:
            findings.append({
                "severity": "error", "code": "CONTRACT_PATH_UNSAFE",
                "path": rel, "message": "Required text path must stay inside the repository.",
            })
            continue
        try:
            text = (repo / candidate).read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            text = ""
        if phrase not in text:
            findings.append({
                "severity": "error", "code": "REQUIRED_TEXT_MISSING",
                "path": rel,
                "message": f"Required contract text was not found: {phrase!r}.",
            })
    return findings
