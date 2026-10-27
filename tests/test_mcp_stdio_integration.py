from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from steadfast.policy import init_policy


class McpStdioIntegrationTests(unittest.TestCase):
    """Exercise the actual newline-delimited MCP transport in a child process."""

    def test_stdio_initialize_list_and_tool_call_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            init_policy(repo)
            requests = [
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {"protocolVersion": "2024-11-05"},
                },
                {"jsonrpc": "2.0", "method": "notifications/initialized"},
                {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
                {
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "tools/call",
                    "params": {"name": "steadfast_discover", "arguments": {}},
                },
            ]
            command = [
                sys.executable,
                "-c",
                "from steadfast.mcp_server import main; raise SystemExit(main())",
                "--repo",
                str(repo),
            ]
            completed = subprocess.run(
                command,
                input="".join(json.dumps(item) + "\n" for item in requests),
                text=True,
                capture_output=True,
                timeout=20,
                check=False,
            )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        responses = [json.loads(line) for line in completed.stdout.splitlines()]
        # The initialized notification must not produce a JSON-RPC response.
        self.assertEqual([item["id"] for item in responses], [1, 2, 3])
        initialized = responses[0]["result"]
        self.assertEqual(initialized["protocolVersion"], "2024-11-05")
        self.assertIn("tools", initialized["capabilities"])
        tools = responses[1]["result"]["tools"]
        self.assertIn("steadfast_discover", {item["name"] for item in tools})
        called = responses[2]["result"]
        self.assertFalse(called["isError"], called["content"])
        payload = json.loads(called["content"][0]["text"])
        self.assertEqual(payload["schema_version"], 1)


    def test_stdio_recovers_from_parse_errors_and_reports_protocol_errors(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            init_policy(repo)
            requests = [
                "{not-json",
                json.dumps({"jsonrpc": "2.0", "id": 7, "method": "not/a/method"}),
                json.dumps({"jsonrpc": "2.0", "method": 42}),
                json.dumps({
                    "jsonrpc": "2.0",
                    "id": 8,
                    "method": "tools/call",
                    "params": {"name": "steadfast_discover", "arguments": {"unexpected": True}},
                }),
                json.dumps({"jsonrpc": "2.0", "id": 9, "method": "ping"}),
            ]
            command = [
                sys.executable,
                "-c",
                "from steadfast.mcp_server import main; raise SystemExit(main())",
                "--repo",
                str(repo),
            ]
            completed = subprocess.run(
                command,
                input="\n".join(requests) + "\n",
                text=True,
                capture_output=True,
                timeout=20,
                check=False,
            )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        responses = [json.loads(line) for line in completed.stdout.splitlines()]
        self.assertEqual(len(responses), 5)
        self.assertEqual(responses[0]["error"]["code"], -32700)
        self.assertEqual(responses[1]["error"]["code"], -32601)
        self.assertEqual(responses[2]["error"]["code"], -32600)
        self.assertIsNone(responses[2]["id"])
        self.assertTrue(responses[3]["result"]["isError"])
        self.assertIn("accepts no arguments", responses[3]["result"]["content"][0]["text"])
        self.assertEqual(responses[4], {"jsonrpc": "2.0", "id": 9, "result": {}})


if __name__ == "__main__":
    unittest.main()
