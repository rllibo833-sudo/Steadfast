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
from steadfast.workcycle import start_cycle


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


    def test_cursor_top_level_shell_command_is_guarded_with_native_schema(self) -> None:
        from io import StringIO
        event = {"command": "git push origin main --force", "cwd": str(self.repo)}
        output = StringIO()
        code = run_hook(self.repo, StringIO(json.dumps(event)), output)
        self.assertEqual(code, 0)
        payload = json.loads(output.getvalue())
        self.assertEqual(payload["permission"], "deny")
        self.assertIn("Force-push", payload["agent_message"])

    def test_claude_pretool_uses_event_specific_deny_schema(self) -> None:
        from io import StringIO
        event = {"hook_event_name": "PreToolUse", "tool_name": "Bash",
                 "tool_input": {"command": "git reset --hard HEAD"}}
        output = StringIO()
        code = run_hook(self.repo, StringIO(json.dumps(event)), output)
        self.assertEqual(code, 0)
        payload = json.loads(output.getvalue())
        self.assertEqual(payload["hookSpecificOutput"]["hookEventName"], "PreToolUse")
        self.assertEqual(payload["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_stop_hook_blocks_active_unverified_cycle(self) -> None:
        from io import StringIO
        (self.repo / ".steadfast" / "goal.md").write_text(
            "# Goal\n\n## Acceptance criteria\n- [ ] Behavior verified\n", encoding="utf-8")
        start_cycle(self.repo, "goal")
        event = {"hook_event_name": "Stop", "reason": "agent finished"}
        output = StringIO()
        code = run_hook(self.repo, StringIO(json.dumps(event)), output)
        self.assertEqual(code, 0)
        payload = json.loads(output.getvalue())
        self.assertEqual(payload["decision"], "block")
        self.assertIn("steadfast cycle verify", payload["reason"])
        self.assertIn("AGENT_COMPLETION_GATE", " ".join(x["code"] for x in evaluate_event(self.repo, event)["findings"]))

    def test_stop_hook_allows_when_no_cycle_is_active(self) -> None:
        from io import StringIO
        output = StringIO()
        code = run_hook(self.repo, StringIO(json.dumps({"hook_event_name": "Stop"})), output)
        self.assertEqual(code, 0)
        self.assertNotEqual(json.loads(output.getvalue()).get("decision"), "block")

    def test_integrations_preserve_existing_files(self) -> None:
        existing = self.repo / "AGENTS.md"
        existing.write_text("user-owned instructions\n", encoding="utf-8")
        result = install_integration(self.repo, "codex")
        self.assertIn("AGENTS.md", result["preserved"])
        self.assertEqual(existing.read_text(encoding="utf-8"), "user-owned instructions\n")
        self.assertTrue((self.repo / ".agents/skills/steadfast-governance/SKILL.md").is_file())

    def test_all_integration_targets_have_configuration(self) -> None:
        for agent in ("claude", "cursor", "codex"):
            generated = integration_files(agent)
            self.assertTrue(generated)
            self.assertTrue(all(content.strip() for content in generated.values()))
        claude_files = integration_files("claude")
        claude = json.loads(claude_files[".claude/settings.local.json"])
        self.assertIn("Stop", claude["hooks"])
        claude_mcp = json.loads(claude_files[".mcp.json"])
        self.assertEqual(claude_mcp["mcpServers"]["steadfast"]["args"],
                         ["-m", "steadfast", "--repo", ".", "mcp-server"])
        cursor_files = integration_files("cursor")
        cursor = json.loads(cursor_files[".cursor/hooks.json"])
        self.assertIn("beforeShellExecution", cursor["hooks"])
        self.assertIn("stop", cursor["hooks"])
        cursor_mcp = json.loads(cursor_files[".cursor/mcp.json"])
        self.assertEqual(cursor_mcp["mcpServers"]["steadfast"]["command"], "python")
        self.assertIn(".mcp.json", integration_files("claude"))
        self.assertIn(".cursor/mcp.json", integration_files("cursor"))

    def test_integration_status_tracks_missing_files(self) -> None:
        status = integration_status(self.repo)
        self.assertFalse(status["claude"]["installed"])
        install_integration(self.repo, "claude")
        self.assertTrue(integration_status(self.repo)["claude"]["installed"])


if __name__ == "__main__":
    unittest.main()
