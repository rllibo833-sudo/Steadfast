from __future__ import annotations
import hashlib
import json
from pathlib import Path
from typing import Any
from .integrations import integration_status

MCP_CONFIG_PATHS = (".mcp.json", ".cursor/mcp.json", ".vscode/mcp.json", ".claude/mcp.json")

def _read_json(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return None, f"{type(exc).__name__}: {exc}"
    if not isinstance(value, dict):
        return None, "Configuration root must be a JSON object"
    return value, None

def _skill_inventory(repo: Path) -> list[dict[str, str]]:
    found: dict[str, dict[str, str]] = {}
    for base in ("skills", ".agents/skills", ".claude/skills", ".cursor/skills"):
        root = repo / base
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("SKILL.md")):
            if not path.is_file():
                continue
            relative = path.relative_to(repo).as_posix()
            try:
                content = path.read_bytes()
                source = content.decode("utf-8")
            except (OSError, UnicodeError):
                found[relative] = {"path": relative, "sha256": "", "name": path.parent.name, "status": "unreadable"}
                continue
            name = path.parent.name
            for line in source.splitlines()[:12]:
                if line.strip().lower().startswith("name:"):
                    name = line.split(":", 1)[1].strip().strip("\\"'") or name
                    break
            found[relative] = {"path": relative, "sha256": hashlib.sha256(content).hexdigest(), "name": name, "status": "indexed"}
    return [found[key] for key in sorted(found)]

def ecosystem_report(repo: Path) -> dict[str, Any]:
    """Build a deterministic, non-executing map of skills and MCP server declarations."""
    root = repo.resolve()
    policy_path = root / ".steadfast" / "policy.json"
    policy, policy_error = _read_json(policy_path) if policy_path.exists() else ({}, None)
    trust = policy.get("ecosystem_trust", {}) if isinstance(policy, dict) else {}
    if not isinstance(trust, dict):
        trust = {}
    trusted_raw, blocked_raw = trust.get("trusted_mcp_servers", []), trust.get("blocked_mcp_servers", [])
    trusted = {v.strip() for v in trusted_raw if isinstance(v, str) and v.strip()} if isinstance(trusted_raw, list) else set()
    blocked = {v.strip() for v in blocked_raw if isinstance(v, str) and v.strip()} if isinstance(blocked_raw, list) else set()
    require_trust = trust.get("require_trust", False) is True
    servers: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for relative in MCP_CONFIG_PATHS:
        path = root / relative
        if not path.exists():
            continue
        config, error = _read_json(path)
        if error:
            errors.append({"path": relative, "error": error})
            continue
        assert config is not None
        raw_servers = config.get("mcpServers", config.get("servers", {}))
        if not isinstance(raw_servers, dict):
            errors.append({"path": relative, "error": "Expected an object under mcpServers or servers"})
            continue
        for name, definition in sorted(raw_servers.items(), key=lambda pair: str(pair[0]).casefold()):
            if not isinstance(name, str) or not name.strip():
                errors.append({"path": relative, "error": "MCP server names must be non-empty strings"})
                continue
            if not isinstance(definition, dict):
                errors.append({"path": relative, "error": f"Server {name!r} must be a JSON object"})
                continue
            command, args = definition.get("command", ""), definition.get("args", [])
            if not isinstance(command, str) or (args is not None and not isinstance(args, list)):
                errors.append({"path": relative, "error": f"Server {name!r} has an invalid command or args shape"})
                continue
            state = "blocked" if name in blocked else "trusted" if name in trusted else "untrusted" if require_trust else "unreviewed"
            servers.append({"name": name, "config_path": relative, "command_basename": Path(command).name if command else "",
                            "argument_count": len(args) if isinstance(args, list) else 0, "status": state})
    counts: dict[str, int] = {}
    for server in servers:
        key = server["name"].casefold()
        counts[key] = counts.get(key, 0) + 1
    duplicates = sorted(name for name, count in counts.items() if count > 1)
    untrusted = sorted(s["name"] + " (" + s["config_path"] + ")" for s in servers if s["status"] in {"blocked", "untrusted", "unreviewed"})
    if policy_error:
        errors.append({"path": ".steadfast/policy.json", "error": policy_error})
    status = "attention_required" if errors or any(s["status"] == "blocked" for s in servers) else "review_required" if untrusted else "indexed"
    return {"schema_version": 1, "repository_root": str(root), "status": status,
            "integrations": integration_status(root), "skills": _skill_inventory(root), "mcp_servers": servers,
            "untrusted_mcp_servers": untrusted, "duplicate_mcp_server_names": duplicates, "configuration_errors": errors,
            "trust_policy": {"require_trust": require_trust, "trusted_mcp_servers": sorted(trusted),
                             "blocked_mcp_servers": sorted(blocked), "source": ".steadfast/policy.json#ecosystem_trust"},
            "safety": {"server_commands_executed": False, "configuration_arguments_returned": False,
                       "note": "This is an inventory and owner-controlled trust check, not a signature or provenance verification."}}
