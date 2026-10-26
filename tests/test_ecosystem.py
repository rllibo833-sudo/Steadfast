from __future__ import annotations
import json
import tempfile
import unittest
from pathlib import Path
from steadfast.ecosystem import ecosystem_report

class EcosystemReportTests(unittest.TestCase):
    def test_indexes_skills_and_labels_mcp_servers_using_owner_policy(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".steadfast").mkdir()
            (root / "skills" / "review").mkdir(parents=True)
            (root / "skills" / "review" / "SKILL.md").write_text("---\nname: review-skill\ndescription: local test\n---\n", encoding="utf-8")
            (root / ".steadfast" / "policy.json").write_text(json.dumps({"version": 1, "ecosystem_trust": {
                "require_trust": True, "trusted_mcp_servers": ["trusted-server"], "blocked_mcp_servers": ["blocked-server"]
            }}), encoding="utf-8")
            (root / ".mcp.json").write_text(json.dumps({"mcpServers": {
                "trusted-server": {"command": "python", "args": ["-m", "server"]},
                "unknown-server": {"command": "node", "args": ["server.js", "--secret", "dont-leak"]},
                "blocked-server": {"command": "blocked", "args": []}
            }}), encoding="utf-8")
            report = ecosystem_report(root)
            states = {item["name"]: item["status"] for item in report["mcp_servers"]}
            self.assertEqual(states, {"blocked-server": "blocked", "trusted-server": "trusted", "unknown-server": "untrusted"})
            self.assertEqual(report["skills"][0]["name"], "review-skill")
            self.assertEqual(report["status"], "attention_required")
            self.assertFalse(report["safety"]["server_commands_executed"])
            self.assertNotIn("dont-leak", json.dumps(report))

    def test_reports_duplicate_names_and_malformed_mcp_config_without_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".mcp.json").write_text(json.dumps({"mcpServers": {"same": {"command": "python", "args": []}}}), encoding="utf-8")
            (root / ".cursor").mkdir()
            (root / ".cursor" / "mcp.json").write_text(json.dumps({"mcpServers": {"same": {"command": "node", "args": []}}}), encoding="utf-8")
            (root / ".vscode").mkdir()
            (root / ".vscode" / "mcp.json").write_text("{not json", encoding="utf-8")
            report = ecosystem_report(root)
            self.assertEqual(report["duplicate_mcp_server_names"], ["same"])
            self.assertEqual(report["status"], "attention_required")
            self.assertEqual(report["configuration_errors"][0]["path"], ".vscode/mcp.json")

if __name__ == "__main__":
    unittest.main()
