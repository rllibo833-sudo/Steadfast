from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from steadfast.integrations import (
    evaluate_event,
    install_integration,
    integration_files,
    integration_status,
    run_hook,
)
from steadfast.policy import init_policy


class AgentGuardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.repo = Path(self.temp.name)
        init_policy(self.repo)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_allowed_source_path_is_allowed(self) -> None:
        result = evaluate_event(self.repo, {
            "tool_name": "Write",
            "tool_input": {"file_path": "src/steadfast/example.py"},
        })
        self.assertEqual(result["decision"], "allow")
        self.assertEqual(result["findings"], [])
        self.assertEqual(result["work_cycle"]["status"], "not_started")

    def test_path_outside_allowlist_is_blocked(self) -> None:
        result = evaluate_event(self.repo, {
            "tool_name": "Write",
            "tool_input": {"file_path": "private-notes.txt"},
        })
        self.assertEqual(result["decision"], "block")
        self.assertEqual(result["findings"][0]["code"], "AGENT_SCOPE_BLOCK")
        self.assertEqual(result["work_cycle"]["status"], "not_started")

    def test_path_escape_is_blocked(self) -> None:
        result = evaluate_event(self.repo, {
            "tool_name": "Write",
            "tool_input": {"file_path": "../outside.txt"},
        })
        self.assertEqual(result["decision"], "block")
        self.assertEqual(result["findings"][0]["code"], "AGENT_PATH_ESCAPE")

    def test_force_push_is_blocked(self) -> None:
        result = evaluate_event(self.repo, {
            "tool_name": "Bash",
            "tool_input": {"command": "git push origin main --force"},
        })
        self.assertEqual(result["decision"], "block")
        self.assertEqual(result["findings"][0]["code"], "AGENT_DESTRUCTIVE_COMMAND")

    def test_command_chain_cannot_hide_hard_reset(self) -> None:
        result = evaluate_event(self.repo, {
            "tool_name": "Bash",
            "tool_input": {"command": "echo safe && git reset --hard HEAD"},
        })
        self.assertEqual(result["decision"], "block")

    def test_invalid_json_hook_fails_closed(self) -> None:
        from io import StringIO
        output = StringIO()
        code = run_hook(self.repo, StringIO("{"), output)
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(output.getvalue())["decision"], "block")

    def test_integrations_preserve_existing_files(self) -> None:
        existing = self.repo / "AGENTS.md"
        existing.write_text("user-owned instructions\n", encoding="utf-8")
        result = install_integration(self.repo, "codex")
        self.assertIn("AGENTS.md", result["preserved"])
        self.assertEqual(existing.read_text(encoding="utf-8"), "user-owned instructions\n")
        self.assertTrue((self.repo / ".codex/skills/steadfast-governance/SKILL.md").is_file())

    def test_all_integration_targets_have_configuration(self) -> None:
        for agent in ("claude", "cursor", "codex"):
            generated = integration_files(agent)
            self.assertTrue(generated)
            self.assertTrue(all(content.strip() for content in generated.values()))
        claude = json.loads(integration_files("claude")[".claude/settings.local.json"])
        self.assertIn("Stop", claude["hooks"])

    def test_integration_status_tracks_missing_files(self) -> None:
        status = integration_status(self.repo)
        self.assertFalse(status["claude"]["installed"])
        install_integration(self.repo, "claude")
        self.assertTrue(integration_status(self.repo)["claude"]["installed"])


if __name__ == "__main__":
    unittest.main()
