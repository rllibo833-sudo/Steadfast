from __future__ import annotations
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from steadfast.policy import init_policy
from steadfast.pipeline import PipelineError
from steadfast.workcycle import start_cycle, attach_evidence, verify_cycle, complete_cycle, block_cycle, cycle_status, cycle_history

class WorkCycleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        init_policy(self.repo)
        (self.repo / ".steadfast" / "goal.md").write_text(
            "# Demo\n\n## Acceptance criteria\n- [ ] Feature works\n- [ ] Regression is covered\n",
            encoding="utf-8")
        (self.repo / "evidence.txt").write_text("observed output\n", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_completion_is_blocked_without_verification(self):
        start_cycle(self.repo, "goal")
        with self.assertRaisesRegex(ValueError, "pipeline"):
            complete_cycle(self.repo)

    def test_completion_requires_all_unchanged_evidence(self):
        start_cycle(self.repo, "goal")
        passed = {"tool":"steadfast","passed":True,"summary":{"passed":1},"steps":[],
                  "manifest":".steadfast/pipeline.json","duration_seconds":0.1}
        with patch("steadfast.workcycle.run_pipeline", return_value=passed):
            with patch("steadfast.workcycle.changed_paths", return_value=[]):
                self.assertTrue(verify_cycle(self.repo)["passed"])
        attach_evidence(self.repo, "AC-01", "evidence.txt")
        with self.assertRaisesRegex(ValueError, "AC-02"):
            complete_cycle(self.repo)
        attach_evidence(self.repo, "AC-02", "evidence.txt")
        (self.repo / "evidence.txt").write_text("modified")
        with self.assertRaisesRegex(ValueError, "AC-01"):
            complete_cycle(self.repo)

    def test_successful_cycle_records_completion(self):
        start_cycle(self.repo, "goal")
        passed = {"tool":"steadfast","passed":True,"summary":{},"steps":[],
                  "manifest":".steadfast/pipeline.json","duration_seconds":0.1}
        with patch("steadfast.workcycle.run_pipeline", return_value=passed):
            with patch("steadfast.workcycle.changed_paths", return_value=[]):
                verify_cycle(self.repo)
        attach_evidence(self.repo, "AC-01", "evidence.txt")
        attach_evidence(self.repo, "AC-02", "evidence.txt")
        self.assertEqual(complete_cycle(self.repo)["status"], "completed")

    def test_workspace_change_after_verification_invalidates_completion(self):
        start_cycle(self.repo, "goal")
        target = self.repo / "implementation.py"
        target.write_text("value = 1\\n", encoding="utf-8")
        passed = {"tool":"steadfast","passed":True,"summary":{},"steps":[],
                  "manifest":".steadfast/pipeline.json","duration_seconds":0.1}
        with patch("steadfast.workcycle.run_pipeline", return_value=passed):
            with patch("steadfast.workcycle.changed_paths", return_value=[]):
                result = verify_cycle(self.repo)
        self.assertTrue(result["workspace_sha256"])
        attach_evidence(self.repo, "AC-01", "evidence.txt")
        attach_evidence(self.repo, "AC-02", "evidence.txt")
        target.write_text("value = 2\\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "workspace changed after verification"):
            complete_cycle(self.repo)

    def test_failed_pipeline_cannot_complete(self):
        start_cycle(self.repo, "goal")
        failed = {"tool":"steadfast","passed":False,"summary":{"failed":1},"steps":[],
                  "manifest":".steadfast/pipeline.json","duration_seconds":0.1}
        with patch("steadfast.workcycle.run_pipeline", return_value=failed):
            with patch("steadfast.workcycle.changed_paths", return_value=[]):
                verify_cycle(self.repo)
        with self.assertRaisesRegex(ValueError, "pipeline"):
            complete_cycle(self.repo)

    def test_active_task_must_be_blocked_or_completed_before_next(self):
        start_cycle(self.repo, "goal")
        with self.assertRaisesRegex(ValueError, "active task"):
            start_cycle(self.repo, "goal")
        block_cycle(self.repo, "waiting for implementation")
        self.assertEqual(start_cycle(self.repo, "goal")["status"], "in_progress")

    def test_journal_detects_tampering(self):
        start_cycle(self.repo, "goal")
        path = self.repo / ".steadfast" / "work-cycle.jsonl"
        record = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
        record["event"] = "forged_completion"
        path.write_text(json.dumps(record) + "\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "integrity|chain"):
            cycle_history(self.repo)

    def test_evidence_rejects_symlink_escape(self):
        outside = self.repo.parent / (self.repo.name + "-outside.txt")
        outside.write_text("outside evidence", encoding="utf-8")
        try:
            (self.repo / "escape.txt").symlink_to(outside)
            start_cycle(self.repo, "goal")
            with self.assertRaisesRegex(ValueError, "symlink|outside"):
                attach_evidence(self.repo, "AC-01", "escape.txt")
        finally:
            outside.unlink(missing_ok=True)

    def test_journal_exposes_event_sequence(self):
        start_cycle(self.repo, "goal")
        attach_evidence(self.repo, "AC-01", "evidence.txt")
        history = cycle_history(self.repo)
        self.assertEqual(history["count"], 2)
        self.assertEqual(history["events"][0]["event"], "evidence_attached")
        self.assertEqual(cycle_status(self.repo)["task"]["acceptance_summary"]["with_evidence"], 1)

if __name__ == "__main__":
    unittest.main()
