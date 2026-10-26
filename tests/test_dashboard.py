from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from steadfast.dashboard import build_snapshot
from steadfast.integrations import evaluate_event
from steadfast.policy import init_policy
from steadfast.session_ledger import record_agent_event


class DashboardSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.repo = Path(self.temp.name)
        init_policy(self.repo)
        (self.repo / ".steadfast" / "goal.md").write_text(
            "# Product\n\n## Acceptance criteria\n- [ ] Console reports current state\n",
            encoding="utf-8",
        )

    def tearDown(self):
        self.temp.cleanup()

    def test_snapshot_includes_agent_session_ledger(self):
        event = {
            "session_id": "session-1",
            "hook_event_name": "PreToolUse",
            "tool_name": "Read",
            "tool_input": {"file_path": "src/steadfast/cli.py"},
        }
        decision = evaluate_event(self.repo, event)
        record_agent_event(self.repo, event, decision)

        snapshot = build_snapshot(self.repo)

        self.assertIn("agent_sessions", snapshot)
        report = snapshot["agent_sessions"]
        self.assertEqual(report["integrity"], "valid")
        self.assertEqual(report["total_events"], 1)
        self.assertEqual(report["sessions"][0]["session_id"], "session-1")
        self.assertEqual(report["events"][0]["tool_name"], "Read")

    def test_snapshot_reports_corrupt_session_ledger_without_crashing(self):
        ledger = self.repo / ".steadfast" / "agent-sessions.jsonl"
        ledger.write_text("{broken\n", encoding="utf-8")

        snapshot = build_snapshot(self.repo)

        self.assertEqual(snapshot["agent_sessions"]["integrity"], "invalid")
        self.assertIn("error", snapshot["agent_sessions"])



    def test_snapshot_includes_work_order_status_and_survives_corrupt_order(self):
        snapshot = build_snapshot(self.repo)
        self.assertIn("work_orders", snapshot)
        self.assertEqual(snapshot["work_orders"]["count"], 0)
        directory = self.repo / ".steadfast" / "work-orders"
        directory.mkdir()
        (directory / "000000000000.json").write_text("{broken", encoding="utf-8")
        snapshot = build_snapshot(self.repo)
        self.assertIn("error", snapshot["work_orders"])

if __name__ == "__main__":
    unittest.main()
