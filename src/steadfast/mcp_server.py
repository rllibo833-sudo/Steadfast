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
        "name": "steadfast_cycle_status",
        "description": "Read the active evidence-gated work cycle.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}
    },
    {
        "name": "steadfast_cycle_start",
        "description": "Start a configured goal as the active evidence-gated work cycle.",
        "inputSchema": {
            "type": "object",
            "properties": {"goal_id": {"type": "string", "minLength": 1}, "title": {"type": "string", "maxLength": 200}},
            "required": ["goal_id"],
            "additionalProperties": False
        }
    },
    {
        "name": "steadfast_cycle_verify",
        "description": "Run configured verification and scope checks for the active work cycle.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}
    },
    {
        "name": "steadfast_cycle_complete",
        "description": "Complete the active work cycle only when configured verification and evidence gates pass.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}
    },
    {
        "name": "steadfast_work_order_issue",
        "description": "Issue an integrity-checked, policy-bounded work order from a configured goal. Writes only Steadfast work-order state.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "goal_id": {"type": "string", "minLength": 1, "maxLength": 120},
                "owner": {"type": "string", "maxLength": 120},
                "ttl_minutes": {"type": "integer", "minimum": 5, "maximum": 10080},
                "scope_paths": {"type": "array", "items": {"type": "string", "minLength": 1}, "minItems": 1}
            },
            "required": ["goal_id"],
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
    if name == "steadfast_cycle_status":
        if arguments:
            raise ValueError("steadfast_cycle_status accepts no arguments")
        return ["cycle", "status"]
    if name == "steadfast_cycle_start":
        unknown = set(arguments) - {"goal_id", "title"}
        if unknown:
            raise ValueError("unknown argument(s): " + ", ".join(sorted(unknown)))
        goal_id = arguments.get("goal_id")
        title = arguments.get("title", "")
        if not isinstance(goal_id, str) or not goal_id.strip():
            raise ValueError("goal_id must be non-empty text")
        if not isinstance(title, str) or len(title) > 200:
            raise ValueError("title must be text of at most 200 characters")
        result = ["cycle", "start", goal_id]
        if title:
            result.extend(["--title", title])
        return result
    if name == "steadfast_cycle_verify":
        if arguments:
            raise ValueError("steadfast_cycle_verify accepts no arguments")
        return ["cycle", "verify"]
    if name == "steadfast_cycle_complete":
        if arguments:
            raise ValueError("steadfast_cycle_complete accepts no arguments")
        return ["cycle", "complete"]
    if name == "steadfast_work_order_issue":
        unknown = set(arguments) - {"goal_id", "owner", "ttl_minutes", "scope_paths"}
        if unknown:
            raise ValueError("unknown argument(s): " + ", ".join(sorted(unknown)))
        goal_id = arguments.get("goal_id")
        owner = arguments.get("owner", "")
        ttl = arguments.get("ttl_minutes", 240)
        scope = arguments.get("scope_paths")
        if not isinstance(goal_id, str) or not goal_id.strip() or len(goal_id) > 120:
            raise ValueError("goal_id must be non-empty text of at most 120 characters")
        if not isinstance(owner, str) or len(owner) > 120:
            raise ValueError("owner must be text of at most 120 characters")
        if isinstance(ttl, bool) or not isinstance(ttl, int) or not 5 <= ttl <= 10080:
            raise ValueError("ttl_minutes must be an integer from 5 to 10080")
        if scope is not None and (not isinstance(scope, list) or not scope or any(not isinstance(p, str) or not p.strip() for p in scope)):
            raise ValueError("scope_paths must be a non-empty array of non-empty strings")
        result = ["work-order", "issue", goal_id, "--ttl-minutes", str(ttl)]
        if owner:
            result.extend(["--owner", owner])
        if scope is not None:
            result.append("--scope")
            result.extend(scope)
        return result
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
                    "Steadfast provides mostly read-only repository governance tools plus bounded work-cycle actions. "
                    "Work-order issuance and cycle lifecycle tools write only Steadfast state after "
                    "validating configured goals and policy. Tools never run arbitrary shell commands "
                    "or edit application source files. Treat heuristic impact results as advisory."
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
