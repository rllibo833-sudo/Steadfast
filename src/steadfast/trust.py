from __future__ import annotations

import json
from pathlib import Path
from typing import Any

KINDS = {"skill", "plugin", "mcp"}


def _string_list(value: Any, field: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value):
        raise ValueError(f"{field} must be a list of non-empty strings")
    if len(value) != len(set(value)):
        raise ValueError(f"{field} must not contain duplicates")
    return value


def evaluate_component_policy(repo: Path, kind: str, name: str, permissions: list[str] | None = None) -> dict[str, Any]:
    """Evaluate explicit owner policy; this never executes a component."""
    if kind not in KINDS:
        raise ValueError("kind must be skill, plugin, or mcp")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("component name must not be empty")
    requested = [] if permissions is None else permissions
    requested = _string_list(requested, "requested permissions")
    policy_path = repo / ".steadfast" / "policy.json"
    if not policy_path.is_file():
        raise FileNotFoundError("Missing .steadfast/policy.json; run steadfast init")
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    if not isinstance(policy, dict) or policy.get("version") != 1:
        raise ValueError("Unsupported or malformed policy")
    trust = policy.get("ecosystem_trust", {})
    if not isinstance(trust, dict):
        raise ValueError("ecosystem_trust must be an object")
    blocked = _string_list(trust.get("blocked_components", []), "ecosystem_trust.blocked_components")
    entries = trust.get("trusted_components", [])
    if not isinstance(entries, list):
        raise ValueError("ecosystem_trust.trusted_components must be a list")
    seen: set[tuple[str, str]] = set()
    normalized_entries: list[dict[str, Any]] = []
    for index, entry in enumerate(entries):
        field = f"ecosystem_trust.trusted_components[{index}]"
        if not isinstance(entry, dict):
            raise ValueError(f"{field} must be an object")
        entry_kind, entry_name = entry.get("kind"), entry.get("name")
        if entry_kind not in KINDS or not isinstance(entry_name, str) or not entry_name.strip():
            raise ValueError(f"{field} must contain a valid kind and non-empty name")
        identity = (entry_kind, entry_name)
        if identity in seen:
            raise ValueError(f"duplicate trusted component: {entry_kind}:{entry_name}")
        seen.add(identity)
        grants = _string_list(entry.get("permissions", []), f"{field}.permissions")
        normalized_entries.append({"kind": entry_kind, "name": entry_name, "permissions": grants})
    key = f"{kind}:{name}"
    if key in blocked:
        decision, reason, grants = "deny", "component is explicitly blocked", []
    else:
        entry = next((x for x in normalized_entries if x["kind"] == kind and x["name"] == name), None)
        grants = sorted(entry["permissions"]) if entry else []
        if entry is None:
            decision, reason = "deny", "no explicit owner approval"
        elif set(requested) - set(grants):
            decision, reason = "deny", "requested permissions exceed owner grant"
        else:
            decision, reason = "allow", "owner policy explicitly approves requested permissions"
    return {
        "schema_version": 1,
        "component": {"kind": kind, "name": name},
        "requested_permissions": sorted(set(requested)),
        "approved_permissions": grants,
        "decision": decision,
        "reason": reason,
        "execution_permitted": False,
        "note": "Policy evaluation is not a sandbox; runtime execution enforcement is not implemented.",
    }
