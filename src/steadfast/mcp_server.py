from __future__ import annotations

import contextlib
import io
import json
import sys
from pathlib import Path
from typing import Any, TextIO

PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {"name": "steadfast", "version": "0.2.0"}

TOOLS: list[dict[str, Any]] = [
    {
        "name": "steadfast_discover",
        "description": "Return Steadfast entrypoints, installed agent integrations, skills and cost constraints.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "steadfast_ecosystem",
        "description": "Inventory repository skills and MCP server declarations; apply owner-configured trust labels without executing integrations.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "steadfast_skill_route",
        "description": "Rank repository SKILL.md files for a natural-language task. Reads skill content but never executes it or claims an agent ran.",
        "inputSchema": {"type": "object", "properties": {"task": {"type": "string", "minLength": 1}, "limit": {"type": "integer", "minimum": 1, "maximum": 25}}, "required": ["task"], "additionalProperties": False},
    },
    {
        "name": "steadfast_trust_check",
        "description": "Evaluate owner-approved permissions for a skill, plugin, or MCP server. This reports policy only and never executes the component.",
        "inputSchema": {"type": "object", "properties": {"kind": {"type": "string", "enum": ["skill", "plugin", "mcp"]}, "name": {"type": "string", "minLength": 1}, "permissions": {"type": "array", "items": {"type": "string", "minLength": 1}}}, "required": ["kind", "name"], "additionalProperties": False},
    },
    {
        "name": "steadfast_report",
        "description": "Run the read-only governance report and return structured JSON findings.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "steadfast_change_impact",
        "description": "Classify changed paths, identify likely test/documentation gaps, and recommend review gates. Path heuristics are advisory, not proof of coverage.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "changed_paths": {
                    "type": "array",
                    "items": {"type": "string", "minLength": 1},
                    "description": "Optional explicit repository-relative paths. Omit to inspect the current Git change set.",
                },
                "base": {"type": "string", "description": "Optional Git base ref for comparison."},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "steadfast_plan",
        "description": "Return the dependency-aware local execution plan, optionally explaining one goal.",
        "inputSchema": {
            "type": "object",
            "properties": {"goal": {"type": "string", "minLength": 1}},
            "additionalProperties": False,
        },
    },
    {
        "name": "steadfast_integrations",
        "description": "Show which supported local coding-agent integrations are installed.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "steadfast_work_orders",
        "description": "List issued agent work orders and their expiry/status without mutating repository state.",
        "inputSchema": {
            "type": "object",
            "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 1000}},
            "additionalProperties": False,
        },
    },
    {
        "name": "steadfast_work_order_show",
        "description": "Read and integrity-check one scoped agent work-order contract.",
        "inputSchema": {
            "type": "object",
            "properties": {"order_id": {"type": "string", "minLength": 12, "maxLength": 12}},
            "required": ["order_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "steadfast_work_order_prompt",
        "description": "Render a copy-ready, scope-bounded execution instruction for a live work order. Does not execute an agent.",
        "inputSchema": {
            "type": "object",
            "properties": {"order_id": {"type": "string", "minLength": 12, "maxLength": 12}},
            "required": ["order_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "steadfast_work_order_issue",
        "description": "Issue a bounded work contract for a configured, dependency-ready goal. This writes a work-order record but does not execute an agent.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "goal_id": {"type": "string", "minLength": 1},
                "owner": {"type": "string", "maxLength": 120},
                "ttl_minutes": {"type": "integer", "minimum": 5, "maximum": 10080},
                "scope_paths": {"type": "array", "items": {"type": "string", "minLength": 1}}
            },
            "required": ["goal_id"],
            "additionalProperties": False
        }
    },
    {
        "name": "steadfast_work_order_verify",
        "description": "Verify a work order's scope and integrity and run the repository's configured validation pipeline. May execute commands from the validated pipeline manifest.",
        "inputSchema": {
            "type": "object",
            "properties": {"order_id": {"type": "string", "minLength": 12, "maxLength": 12}},
            "required": ["order_id"],
            "additionalProperties": False
        }
    },
    {
        "name": "steadfast_work_order_close",
        "description": "Close a work order only after successful verification.",
        "inputSchema": {
            "type": "object",
            "properties": {"order_id": {"type": "string", "minLength": 12, "maxLength": 12}},
            "required": ["order_id"],
            "additionalProperties": False
        }
    },
    {
        "name": "steadfast_inventory",
        "description": "Return a repository inventory and implementation-budget summary.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
]


def _tool_args(name: str, arguments: Any) -> list[str]:
    if not isinstance(arguments, dict):
        raise ValueError("tool arguments must be a JSON object")
    if name == "steadfast_discover":
        if arguments:
            raise ValueError("steadfast_discover accepts no arguments")
        return ["discover"]
    if name == "steadfast_ecosystem":
        if arguments:
            raise ValueError("steadfast_ecosystem accepts no arguments")
        return ["ecosystem"]
    if name == "steadfast_skill_route":
        unknown = set(arguments) - {"task", "limit"}
        if unknown:
            raise ValueError("unknown argument(s): " + ", ".join(sorted(unknown)))
        task = arguments.get("task")
        limit = arguments.get("limit", 5)
        if not isinstance(task, str) or not task.strip():
            raise ValueError("task must be a non-empty string")
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 25:
            raise ValueError("limit must be an integer from 1 to 25")
        return ["skills", "route", task, "--limit", str(limit)]
    if name == "steadfast_trust_check":
        unknown = set(arguments) - {"kind", "name", "permissions"}
        if unknown:
            raise ValueError("unknown argument(s): " + ", ".join(sorted(unknown)))
        kind, component_name = arguments.get("kind"), arguments.get("name")
        permissions = arguments.get("permissions", [])
        if kind not in {"skill", "plugin", "mcp"} or not isinstance(component_name, str) or not component_name.strip():
            raise ValueError("kind and non-empty name are required")
        if not isinstance(permissions, list) or any(not isinstance(item, str) or not item.strip() for item in permissions):
            raise ValueError("permissions must be an array of non-empty strings")
        result = ["trust-check", "--kind", kind, "--name", component_name]
        for permission in permissions:
            result.extend(["--permission", permission])
        return result
    if name == "steadfast_report":
        if arguments:
            raise ValueError("steadfast_report accepts no arguments")
        return ["report", "--format", "json"]
    if name == "steadfast_change_impact":
        unknown = set(arguments) - {"changed_paths", "base"}
        if unknown:
            raise ValueError("unknown argument(s): " + ", ".join(sorted(unknown)))
        paths = arguments.get("changed_paths")
        if paths is not None and (
            not isinstance(paths, list)
            or any(not isinstance(item, str) or not item.strip() for item in paths)
        ):
            raise ValueError("changed_paths must be an array of non-empty strings")
        base = arguments.get("base")
        if base is not None and (not isinstance(base, str) or not base.strip()):
            raise ValueError("base must be a non-empty string")
        result = ["impact-check"]
        if base is not None:
            result.extend(["--base", base])
        if paths is not None:
            result.append("--changed")
            result.extend(paths)
        return result
    if name == "steadfast_plan":
        unknown = set(arguments) - {"goal"}
        if unknown:
            raise ValueError("unknown argument(s): " + ", ".join(sorted(unknown)))
        goal = arguments.get("goal")
        if goal is not None and (not isinstance(goal, str) or not goal.strip()):
            raise ValueError("goal must be a non-empty string")
        result = ["plan"]
        if goal is not None:
            result.extend(["--goal", goal])
        return result
    if name == "steadfast_integrations":
        if arguments:
            raise ValueError("steadfast_integrations accepts no arguments")
        return ["integration-status"]
    if name == "steadfast_work_orders":
        unknown = set(arguments) - {"limit"}
        if unknown:
            raise ValueError("unknown argument(s): " + ", ".join(sorted(unknown)))
        limit = arguments.get("limit", 100)
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 1000:
            raise ValueError("limit must be an integer from 1 to 1000")
        return ["work-order", "list", "--limit", str(limit)]
    if name == "steadfast_work_order_show":
        unknown = set(arguments) - {"order_id"}
        if unknown:
            raise ValueError("unknown argument(s): " + ", ".join(sorted(unknown)))
        order_id = arguments.get("order_id")
        if not isinstance(order_id, str) or len(order_id) != 12 or any(c not in "0123456789abcdef" for c in order_id):
            raise ValueError("order_id must be 12 lowercase hexadecimal characters")
        return ["work-order", "show", order_id]
    if name == "steadfast_work_order_prompt":
        unknown = set(arguments) - {"order_id"}
        if unknown:
            raise ValueError("unknown argument(s): " + ", ".join(sorted(unknown)))
        order_id = arguments.get("order_id")
        if not isinstance(order_id, str) or len(order_id) != 12 or any(ch not in "0123456789abcdef" for ch in order_id):
            raise ValueError("order_id must be 12 lowercase hexadecimal characters")
        return ["work-order", "prompt", order_id]
    if name == "steadfast_work_order_issue":
        unknown = set(arguments) - {"goal_id", "owner", "ttl_minutes", "scope_paths"}
        if unknown:
            raise ValueError("unknown argument(s): " + ", ".join(sorted(unknown)))
        goal_id = arguments.get("goal_id")
        owner = arguments.get("owner", "")
        ttl = arguments.get("ttl_minutes", 240)
        scope = arguments.get("scope_paths")
        if not isinstance(goal_id, str) or not goal_id.strip():
            raise ValueError("goal_id must be a non-empty string")
        if not isinstance(owner, str) or len(owner) > 120:
            raise ValueError("owner must be text of at most 120 characters")
        if isinstance(ttl, bool) or not isinstance(ttl, int) or not 5 <= ttl <= 10080:
            raise ValueError("ttl_minutes must be an integer from 5 to 10080")
        if scope is not None and (not isinstance(scope, list) or any(not isinstance(p, str) or not p.strip() for p in scope)):
            raise ValueError("scope_paths must be an array of non-empty strings")
        result = ["work-order", "issue", goal_id, "--owner", owner, "--ttl-minutes", str(ttl)]
        if scope is not None:
            result.append("--scope")
            result.extend(scope)
        return result
    if name in {"steadfast_work_order_verify", "steadfast_work_order_close"}:
        unknown = set(arguments) - {"order_id"}
        if unknown:
            raise ValueError("unknown argument(s): " + ", ".join(sorted(unknown)))
        order_id = arguments.get("order_id")
        if not isinstance(order_id, str) or len(order_id) != 12 or any(c not in "0123456789abcdef" for c in order_id):
            raise ValueError("order_id must be 12 lowercase hexadecimal characters")
        action = "verify" if name.endswith("_verify") else "close"
        return ["work-order", action, order_id]
    if name == "steadfast_inventory":
        if arguments:
            raise ValueError("steadfast_inventory accepts no arguments")
        return ["inventory"]
    raise ValueError(f"unknown tool: {name}")


def handle_message(message: Any, repo: Path) -> dict[str, Any] | None:
    """Handle one MCP JSON-RPC message; return None for notifications."""
    if not isinstance(message, dict):
        return {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "Invalid Request"}}
    method = message.get("method")
    request_id = message.get("id")
    is_notification = "id" not in message
    if message.get("jsonrpc") != "2.0" or not isinstance(method, str):
        return None if is_notification else {
            "jsonrpc": "2.0", "id": request_id,
            "error": {"code": -32600, "message": "Invalid Request"},
        }
    if is_notification:
        return None
    if method == "initialize":
        params = message.get("params") or {}
        requested = params.get("protocolVersion", PROTOCOL_VERSION) if isinstance(params, dict) else PROTOCOL_VERSION
        version = requested if isinstance(requested, str) and requested else PROTOCOL_VERSION
        return {
            "jsonrpc": "2.0", "id": request_id,
            "result": {
                "protocolVersion": version,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": SERVER_INFO,
                "instructions": (
                    "Steadfast provides read-only repository governance tools and an explicit scoped work-order lifecycle. "
                    "Issuing and closing work orders update only Steadfast control records. The work-order verify tool runs the configured validated pipeline, which may execute commands from the repository's pipeline manifest. "
                    "The ecosystem inventory never executes configured MCP server commands. Tools do not edit application source files. Treat heuristic impact results as advisory."
                ),
            },
        }
    if method == "ping":
        return {"jsonrpc": "2.0", "id": request_id, "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": request_id, "result": {"tools": TOOLS}}
    if method == "tools/call":
        params = message.get("params")
        if not isinstance(params, dict) or not isinstance(params.get("name"), str):
            return {"jsonrpc": "2.0", "id": request_id,
                    "error": {"code": -32602, "message": "tools/call requires a tool name"}}
        name = params["name"]
        try:
            args = _tool_args(name, params.get("arguments", {}))
            # Invoke the existing CLI handlers so the MCP interface shares the
            # same policy and reporting behavior as the command-line interface.
            from .cli import main
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                exit_code = main(["--repo", str(repo), *args])
            text = output.getvalue().strip()
            payload: Any
            try:
                payload = json.loads(text) if text else {"message": "Command completed without output"}
            except json.JSONDecodeError:
                payload = {"output": text}
            result = {
                "content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False, indent=2)}],
                "isError": exit_code != 0,
            }
            return {"jsonrpc": "2.0", "id": request_id, "result": result}
        except (ValueError, OSError, RuntimeError) as exc:
            return {
                "jsonrpc": "2.0", "id": request_id,
                "result": {"content": [{"type": "text", "text": str(exc)}], "isError": True},
            }
    return {"jsonrpc": "2.0", "id": request_id,
            "error": {"code": -32601, "message": f"Method not found: {method}"}}


def serve_stdio(repo: Path, stdin: TextIO = sys.stdin, stdout: TextIO = sys.stdout) -> int:
    """Run the newline-delimited JSON-RPC transport used by MCP stdio clients."""
    root = repo.resolve()
    for line in stdin:
        if not line.strip():
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError as exc:
            response = {"jsonrpc": "2.0", "id": None,
                        "error": {"code": -32700, "message": f"Parse error: {exc.msg}"}}
        else:
            response = handle_message(message, root)
        if response is not None:
            stdout.write(json.dumps(response, ensure_ascii=False, separators=(",", ":")) + "\n")
            stdout.flush()
    return 0


def main() -> int:
    """Console entry point for MCP stdio; repository root is the current directory."""
    import argparse

    parser = argparse.ArgumentParser(prog="steadfast-mcp")
    parser.add_argument("--repo", default=".", help="Repository root (default: current directory)")
    args = parser.parse_args()
    return serve_stdio(Path(args.repo), stdin=sys.stdin, stdout=sys.stdout)
