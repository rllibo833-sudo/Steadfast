from __future__ import annotations

import json
from pathlib import Path
from typing import Any

KINDS = {"skill", "plugin", "mcp"}


def evaluate_component_policy(repo: Path, kind: str, name: str, permissions: list[str] | None = None) -> dict[str, Any]:
    """Evaluate explicit owner policy; this never executes a component."""
    if kind not in KINDS:
        raise ValueError("kind must be skill, plugin, or mcp")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("component name must not be empty")
    requested = permissions or []
    if not isinstance(requested, list) or any(not isinstance(p, str) or not p.strip() for p in requested):
        raise ValueError("permissions must be a list of non-empty strings")
    policy_path = repo / ".steadfast" / "policy.json"
    if not policy_path.is_file():
        raise FileNotFoundError("Missing .steadfast/policy.json; run steadfast init")
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    if not isinstance(policy, dict) or policy.get("version") != 1:
        raise ValueError("Unsupported or malformed policy")
    trust = policy.get("ecosystem_trust", {})
    if not isinstance(trust, dict):
        raise ValueError("ecosystem_trust must be an object")
    key = f"{kind}:{name}"
    if key in trust.get("blocked_components", []):
        decision, reason, grants = "deny", "component is explicitly blocked", []
    else:
        entries = trust.get("trusted_components", [])
        entry = next((x for x in entries if isinstance(x, dict) and x.get("kind") == kind and x.get("name") == name), None)
        grants = sorted(set(entry.get("permissions", []))) if entry else []
        if entry is None:
            decision, reason = "deny", "no explicit owner approval"
        elif set(requested) - set(grants):
            decision, reason = "deny", "requested permissions exceed owner grant"
        else:
            decision, reason = "allow", "owner policy explicitly approves requested permissions"
    return {"schema_version": 1, "component": {"kind": kind, "name": name}, "requested_permissions": sorted(set(requested)), "approved_permissions": grants, "decision": decision, "reason": reason, "execution_permitted": False, "note": "Policy evaluation is not a sandbox; runtime execution enforcement is not implemented."}
