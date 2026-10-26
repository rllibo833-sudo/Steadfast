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

    def test_indexes_codex_toml_mcp_servers_without_leaking_arguments(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            codex = root / ".codex"
            codex.mkdir()
            (codex / "config.toml").write_text(
                '[mcp_servers.steadfast]\ncommand = "python"\nargs = ["-m", "steadfast", "--token", "hidden"]\n'
                'cwd = "."\nstartup_timeout_sec = 10\n\n[mcp_servers.review_bot]\ncommand = "node"\nargs = ["review.js"]\n',
                encoding="utf-8",
            )
            report = ecosystem_report(root)
            indexed = {item["name"]: item for item in report["mcp_servers"]}
            self.assertEqual(indexed["steadfast"]["config_path"], ".codex/config.toml")
            self.assertEqual(indexed["steadfast"]["command_basename"], "python")
            self.assertEqual(indexed["steadfast"]["argument_count"], 4)
            self.assertNotIn("hidden", json.dumps(report))
            self.assertEqual(indexed["review_bot"]["status"], "unreviewed")

    def test_reports_invalid_codex_command_value(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".codex").mkdir()
            (root / ".codex" / "config.toml").write_text('[mcp_servers.bad]\ncommand = ["not", "a", "string"]\n', encoding="utf-8")
            report = ecosystem_report(root)
            self.assertEqual(report["configuration_errors"][0]["path"], ".codex/config.toml")
            self.assertEqual(report["status"], "attention_required")

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


    def test_extension_inventory_reads_entry_point_metadata(self):
        from unittest.mock import patch
        from steadfast.ecosystem import extension_inventory

        class Point:
            def __init__(self, name, value, group, dist_name="sample", version="1.2"):
                self.name, self.value, self.group = name, value, group
                self.dist = type("Dist", (), {"name": dist_name, "version": version})()

        class Points(list):
            def select(self, *, group):
                return [point for point in self if point.group == group]

        points = Points([
            Point("demo", "external:plugin", "steadfast.plugins"),
            Point("scope-guard", "steadfast.integrations:scope_guard_skill", "steadfast.skills"),
            Point("server", "server:main", "mcp.servers"),
        ])
        with patch("steadfast.ecosystem.metadata.entry_points", return_value=points):
            result = extension_inventory()
        self.assertEqual(result["plugins"][0]["name"], "demo")
        self.assertEqual(result["skills"][0]["name"], "scope-guard")
        self.assertEqual(result["mcp_servers"][0]["name"], "server")
        self.assertEqual(result["discovery_policy"], "metadata_only_no_provider_code_executed")

if __name__ == "__main__":
    unittest.main()
