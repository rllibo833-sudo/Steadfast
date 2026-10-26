from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from steadfast.session_ledger import SessionLedgerError, record_agent_event, session_report, verify_session_ledger
from steadfast.integrations import run_hook
from steadfast.policy import init_policy


class SessionLedgerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        init_policy(self.repo)

    def tearDown(self):
        self.tmp.cleanup()

    def test_records_agent_events_and_aggregates_sessions(self):
        decision = {"decision": "allow", "findings": [], "work_cycle": {"status": "in_progress"}}
        record_agent_event(self.repo, {"session_id": "s-1", "hook_event_name": "PreToolUse",
                                      "tool_name": "Write", "tool_input": {"file_path": "src/main.py"}}, decision)
        record_agent_event(self.repo, {"session_id": "s-1", "hook_event_name": "PreToolUse",
                                      "tool_name": "Bash", "tool_input": {"command": "pytest"}}, 
                           {"decision": "block", "findings": [{"code": "AGENT_SCOPE_BLOCK"}]})
        report = session_report(self.repo)
        self.assertEqual(report["total_events"], 2)
        self.assertEqual(report["decisions"], {"allow": 1, "block": 1})
        self.assertEqual(report["sessions"][0]["blocked"], 1)
        self.assertEqual(verify_session_ledger(self.repo)["events_verified"], 2)

    def test_sensitive_command_values_are_redacted(self):
        record_agent_event(self.repo, {"tool_name": "Bash",
                                      "tool_input": {"command": "deploy --api-key=supersecret Bearer abc.def"}}, 
                           {"decision": "allow", "findings": []})
        raw = (self.repo / ".steadfast" / "agent-sessions.jsonl").read_text(encoding="utf-8")
        self.assertNotIn("supersecret", raw)
        self.assertNotIn("abc.def", raw)
        self.assertIn("[REDACTED]", raw)


    def test_agent_hook_records_decision_before_returning(self):
        from io import StringIO
        output = StringIO()
        code = run_hook(self.repo, StringIO(json.dumps({"tool_name": "Read", "tool_input": {"file_path": "src/main.py"}})), output)
        self.assertEqual(code, 0)
        result = json.loads(output.getvalue())
        self.assertIn("decision", result)
        report = verify_session_ledger(self.repo)
        self.assertEqual(report["events_verified"], 1)

    def test_hash_chain_detects_record_tampering(self):
        record_agent_event(self.repo, {"tool_name": "Read", "tool_input": {"file_path": "src/a.py"}},
                           {"decision": "allow", "findings": []})
        path = self.repo / ".steadfast" / "agent-sessions.jsonl"
        record = json.loads(path.read_text(encoding="utf-8"))
        record["decision"] = "block"
        path.write_text(json.dumps(record) + "\n", encoding="utf-8")
        with self.assertRaisesRegex(SessionLedgerError, "hash"):
            verify_session_ledger(self.repo)

    def test_filter_and_limit_are_validated(self):
        for sid in ("a", "b"):
            record_agent_event(self.repo, {"session_id": sid, "tool_name": "Read"},
                               {"decision": "allow", "findings": []})
        self.assertEqual(session_report(self.repo, session_id="a")["total_events"], 1)
        with self.assertRaisesRegex(SessionLedgerError, "limit"):
            session_report(self.repo, limit=0)

    def test_secret_fields_are_redacted_recursively(self):
        record_agent_event(self.repo, {"tool_input": {"nested": {"access_token": "do-not-store", "path": "src/a.py"}},
                                      "tool_name": "Read"}, {"decision": "allow", "findings": []})
        raw = (self.repo / ".steadfast" / "agent-sessions.jsonl").read_text(encoding="utf-8")
        self.assertNotIn("do-not-store", raw)
        self.assertIn("[REDACTED]", raw)


if __name__ == "__main__":
    unittest.main()
