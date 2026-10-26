from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from steadfast.mcp_server import handle_message, _tool_args
from steadfast.policy import init_policy


class McpServerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.repo = Path(self.temp.name)
        init_policy(self.repo)

    def tearDown(self):
        self.temp.cleanup()

    def test_initialize_advertises_read_only_tools_capability(self):
        response = handle_message(
            {"jsonrpc": "2.0", "id": 1, "method": "initialize",
             "params": {"protocolVersion": "2024-11-05"}},
            self.repo,
        )
        self.assertEqual(response["result"]["protocolVersion"], "2024-11-05")
        self.assertIn("tools", response["result"]["capabilities"])
        self.assertIn("read-only", response["result"]["instructions"])

    def test_tools_list_exposes_discovery_and_impact_tools(self):
        response = handle_message(
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, self.repo
        )
        names = {item["name"] for item in response["result"]["tools"]}
        self.assertIn("steadfast_discover", names)
        self.assertIn("steadfast_change_impact", names)
        self.assertIn("steadfast_report", names)
        self.assertIn("steadfast_ecosystem", names)

    def test_discover_tool_returns_machine_readable_payload(self):
        response = handle_message(
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
             "params": {"name": "steadfast_discover", "arguments": {}}},
            self.repo,
        )
        self.assertFalse(response["result"]["isError"])
        payload = json.loads(response["result"]["content"][0]["text"])
        self.assertEqual(payload["schema_version"], 1)
        self.assertFalse(payload["cost_policy"]["paid_runner_required"])

    def test_ecosystem_tool_routes_to_read_only_inventory(self):
        self.assertEqual(_tool_args("steadfast_ecosystem", {}), ["ecosystem"])
        with self.assertRaisesRegex(ValueError, "accepts no arguments"):
            _tool_args("steadfast_ecosystem", {"execute": True})

    def test_tool_rejects_unknown_arguments(self):
        response = handle_message(
            {"jsonrpc": "2.0", "id": 4, "method": "tools/call",
             "params": {"name": "steadfast_report", "arguments": {"shell": "whoami"}}},
            self.repo,
        )
        self.assertTrue(response["result"]["isError"])
        self.assertIn("accepts no arguments", response["result"]["content"][0]["text"])

    def test_notifications_do_not_emit_responses(self):
        response = handle_message(
            {"jsonrpc": "2.0", "method": "notifications/initialized"}, self.repo
        )
        self.assertIsNone(response)



    def test_work_order_tools_are_discoverable_and_read_only(self):
        response = handle_message(
            {"jsonrpc": "2.0", "id": 5, "method": "tools/list"}, self.repo
        )
        names = {item["name"] for item in response["result"]["tools"]}
        self.assertIn("steadfast_work_orders", names)
        self.assertIn("steadfast_work_order_show", names)
        listed = handle_message(
            {"jsonrpc": "2.0", "id": 6, "method": "tools/call",
             "params": {"name": "steadfast_work_orders", "arguments": {"limit": 10}}},
            self.repo,
        )
        self.assertFalse(listed["result"]["isError"])
        self.assertEqual(json.loads(listed["result"]["content"][0]["text"])["count"], 0)

    def test_work_order_show_rejects_invalid_id_before_dispatch(self):
        with self.assertRaisesRegex(ValueError, "12 lowercase hexadecimal"):
            _tool_args("steadfast_work_order_show", {"order_id": "../bad"})
        response = handle_message(
            {"jsonrpc": "2.0", "id": 7, "method": "tools/call",
             "params": {"name": "steadfast_work_order_show", "arguments": {"order_id": "../bad"}}},
            self.repo,
        )
        self.assertTrue(response["result"]["isError"])


if __name__ == "__main__":
    unittest.main()
