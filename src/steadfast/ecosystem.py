from __future__ import annotations
import ast
import hashlib
import json
from pathlib import Path
from typing import Any
from .integrations import integration_status
from .skill_router import read_skill_metadata

MCP_CONFIG_PATHS = (".mcp.json", ".cursor/mcp.json", ".vscode/mcp.json", ".claude/mcp.json")
CODEX_CONFIG_PATH = ".codex/config.toml"

def _read_json(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return None, f"{type(exc).__name__}: {exc}"
    if not isinstance(value, dict):
        return None, "Configuration root must be a JSON object"
    return value, None

def _read_codex_toml(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    """Read the MCP subset of Codex TOML without adding a runtime dependency."""
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        return None, f"{type(exc).__name__}: {exc}"
    servers: dict[str, dict[str, Any]] = {}
    current: dict[str, Any] | None = None
    for number, raw in enumerate(source.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[mcp_servers.") and line.endswith("]"):
            name = line[len("[mcp_servers."):-1]
            if not name or any(char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for char in name):
                return None, f"Invalid MCP server section at line {number}"
            if name in servers:
                return None, f"Duplicate MCP server section {name!r} at line {number}"
            current = {}
            servers[name] = current
            continue
        if line.startswith("["):
            current = None
            continue
        if current is None:
            continue
        key, separator, raw_value = line.partition("=")
        key, raw_value = key.strip(), raw_value.strip()
        if key not in {"command", "args"}:
            continue
        if not separator:
            return None, f"Invalid {key} setting at line {number}"
        try:
            value = ast.literal_eval(raw_value)
        except (ValueError, SyntaxError):
            return None, f"Invalid TOML value for {key!r} at line {number}"
        if key == "command" and not isinstance(value, str):
            return None, f"command must be a string at line {number}"
        if key == "args" and (not isinstance(value, list) or any(not isinstance(item, str) for item in value)):
            return None, f"args must be an array of strings at line {number}"
        current[key] = value
    return {"mcpServers": servers}, None


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
            metadata, _ = read_skill_metadata(source)
            name = metadata.get("name") or path.parent.name
            found[relative] = {"path": relative, "sha256": hashlib.sha256(content).hexdigest(), "name": name, "status": "indexed"}
    return [found[key] for key in sorted(found)]


from importlib import metadata


def _entry_point_records(group: str) -> list[dict[str, str]]:
    """Read installed extension metadata without importing or executing providers."""
    try:
        points = metadata.entry_points()
        selected = points.select(group=group) if hasattr(points, "select") else points.get(group, [])
    except (ImportError, OSError, ValueError):
        return []
    records = []
    for point in selected:
        distribution = getattr(point, "dist", None)
        records.append({
            "name": str(point.name),
            "value": str(point.value),
            "group": group,
            "distribution": str(getattr(distribution, "name", "") or ""),
            "version": str(getattr(distribution, "version", "") or ""),
            "status": "discovered_not_loaded",
        })
    return sorted(records, key=lambda item: (item["name"].casefold(), item["distribution"].casefold(), item["value"]))


def discover_plugins() -> dict[str, Any]:
    """Return metadata for installed Steadfast plugins; never import third-party code."""
    records = _entry_point_records("steadfast.plugins")
    return {"schema_version": 1, "plugins": [item for item in records if item["name"] != "auto"],
            "loaded": False, "note": "Plugin entry points are inventoried only; discovery does not execute third-party code."}


def extension_inventory() -> dict[str, Any]:
    return {
        "skills": _entry_point_records("steadfast.skills"),
        "plugins": discover_plugins()["plugins"],
        "mcp_servers": _entry_point_records("mcp.servers"),
        "discovery_policy": "metadata_only_no_provider_code_executed",
    }

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
    codex_path = root / CODEX_CONFIG_PATH
    if codex_path.exists():
        config, error = _read_codex_toml(codex_path)
        if error:
            errors.append({"path": CODEX_CONFIG_PATH, "error": error})
        else:
            assert config is not None
            for name, definition in sorted(config["mcpServers"].items(), key=lambda pair: pair[0].casefold()):
                command, args = definition.get("command", ""), definition.get("args", [])
                state = "blocked" if name in blocked else "trusted" if name in trusted else "untrusted" if require_trust else "unreviewed"
                servers.append({"name": name, "config_path": CODEX_CONFIG_PATH,
                                "command_basename": Path(command).name if command else "",
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
    trusted_components = trust.get("trusted_components", []) if isinstance(trust.get("trusted_components", []), list) else []
    blocked_components = trust.get("blocked_components", []) if isinstance(trust.get("blocked_components", []), list) else []
    return {"schema_version": 1, "repository_root": str(root), "status": status,
            "integrations": integration_status(root), "skills": _skill_inventory(root), "mcp_servers": servers,
            "installed_extensions": extension_inventory(),
            "component_policy": {"trusted_components": trusted_components, "blocked_components": blocked_components,
                                 "policy_source": ".steadfast/policy.json#ecosystem_trust",
                                 "execution_enforcement": "not_implemented"},
            "untrusted_mcp_servers": untrusted, "duplicate_mcp_server_names": duplicates, "configuration_errors": errors,
            "trust_policy": {"require_trust": require_trust, "trusted_mcp_servers": sorted(trusted),
                             "blocked_mcp_servers": sorted(blocked), "source": ".steadfast/policy.json#ecosystem_trust"},
            "safety": {"server_commands_executed": False, "configuration_arguments_returned": False,
                       "note": "This is an inventory and owner-controlled trust check, not a signature or provenance verification."}}
