from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from steadfast.trust import evaluate_component_policy


class ComponentPolicyTests(unittest.TestCase):
    def make_repo(self, policy):
        temporary = tempfile.TemporaryDirectory()
        root = Path(temporary.name)
        (root / ".steadfast").mkdir()
        (root / ".steadfast" / "policy.json").write_text(json.dumps(policy), encoding="utf-8")
        self.addCleanup(temporary.cleanup)
        return root

    def test_unregistered_component_is_denied_by_default(self):
        root = self.make_repo({"version": 1, "ecosystem_trust": {}})
        result = evaluate_component_policy(root, "plugin", "unknown", ["repo:read"])
        self.assertEqual(result["decision"], "deny")
        self.assertFalse(result["execution_permitted"])

    def test_explicit_grant_does_not_grant_unrequested_capabilities(self):
        root = self.make_repo({"version": 1, "ecosystem_trust": {"trusted_components": [{"kind": "plugin", "name": "formatter", "permissions": ["repo:read", "repo:write"]}]}})
        allowed = evaluate_component_policy(root, "plugin", "formatter", ["repo:read"])
        denied = evaluate_component_policy(root, "plugin", "formatter", ["network:outbound"])
        self.assertEqual(allowed["decision"], "allow")
        self.assertFalse(allowed["execution_permitted"])
        self.assertEqual(denied["decision"], "deny")

    def test_block_overrides_grant(self):
        root = self.make_repo({"version": 1, "ecosystem_trust": {"trusted_components": [{"kind": "mcp", "name": "review", "permissions": ["repo:read"]}], "blocked_components": ["mcp:review"]}})
        result = evaluate_component_policy(root, "mcp", "review", ["repo:read"])
        self.assertEqual(result["decision"], "deny")
        self.assertIn("blocked", result["reason"])

    def test_rejects_invalid_kind_and_permissions(self):
        root = self.make_repo({"version": 1, "ecosystem_trust": {}})
        with self.assertRaises(ValueError):
            evaluate_component_policy(root, "shell", "anything")
        with self.assertRaises(ValueError):
            evaluate_component_policy(root, "skill", "anything", [""])


    def test_cli_trust_check_uses_owner_policy(self):
        from steadfast.cli import main
        root = self.make_repo({"version": 1, "ecosystem_trust": {"trusted_components": [{"kind": "skill", "name": "review", "permissions": ["repo:read"]}]}})
        self.assertEqual(main(["--repo", str(root), "trust-check", "--kind", "skill", "--name", "review", "--permission", "repo:read"]), 0)
        self.assertEqual(main(["--repo", str(root), "trust-check", "--kind", "skill", "--name", "review", "--permission", "repo:write"]), 1)

    def test_mcp_tool_maps_to_the_same_cli_policy(self):
        from steadfast.mcp_server import TOOLS, _tool_args
        tool = next(item for item in TOOLS if item["name"] == "steadfast_trust_check")
        self.assertEqual(tool["inputSchema"]["required"], ["kind", "name"])
        self.assertEqual(_tool_args("steadfast_trust_check", {"kind": "plugin", "name": "format", "permissions": ["repo:read"]}), ["trust-check", "--kind", "plugin", "--name", "format", "--permission", "repo:read"])

if __name__ == "__main__":
    unittest.main()
