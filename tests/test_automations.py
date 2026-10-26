from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from steadfast.automations import (
    automation_history, list_automations, run_automation, _validate_workflows,
)
from steadfast.policy import init_policy


class AutomationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.repo = Path(self.temp.name)
        init_policy(self.repo)
        (self.repo / ".steadfast" / "goal.md").write_text(
            "# Goal\n\n## Acceptance criteria\n- [ ] A real workflow runs\n",
            encoding="utf-8",
        )

    def tearDown(self):
        self.temp.cleanup()

    def test_builtin_workflows_are_available_without_manifest_or_keys(self):
        result = list_automations(self.repo)
        self.assertEqual(result["source"], "built-in")
        self.assertGreaterEqual(len(result["workflows"]), 3)
        self.assertIn("audit", [x["id"] for x in result["available_actions"]])

    def test_custom_manifest_accepts_only_registered_actions(self):
        manifest = self.repo / ".steadfast" / "automations.json"
        manifest.write_text(json.dumps({"schema_version": 1, "workflows": [
            {"id": "my-check", "name": "My check", "steps": ["audit"]}
        ]}), encoding="utf-8")
        self.assertEqual(list_automations(self.repo)["workflows"][0]["id"], "my-check")
        manifest.write_text(json.dumps({"schema_version": 1, "workflows": [
            {"id": "unsafe", "name": "Unsafe", "steps": ["shell"]}
        ]}), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "unsupported action"):
            list_automations(self.repo)

    def test_duplicate_ids_and_empty_steps_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "duplicate"):
            _validate_workflows([
                {"id": "same", "name": "One", "steps": ["audit"]},
                {"id": "same", "name": "Two", "steps": ["audit"]},
            ])
        with self.assertRaisesRegex(ValueError, "needs 1-12 steps"):
            _validate_workflows([{"id": "empty", "name": "Empty", "steps": []}])

    def test_run_records_actual_action_results_and_history(self):
        result = run_automation(self.repo, "quick-health")
        self.assertEqual(result["workflow_id"], "quick-health")
        self.assertGreaterEqual(result["step_count"], 1)
        self.assertIn(result["steps"][0]["status"], {"passed", "failed", "error"})
        history = automation_history(self.repo)
        self.assertEqual(history["count"], 1)
        self.assertEqual(history["runs"][0]["run_id"], result["run_id"])

    def test_unknown_workflow_does_not_create_history(self):
        with self.assertRaisesRegex(ValueError, "unknown automation"):
            run_automation(self.repo, "not-real")
        self.assertEqual(automation_history(self.repo)["count"], 0)

    def test_manifest_symlink_inside_repository_is_rejected(self):
        real = self.repo / ".steadfast" / "real.json"
        real.write_text(json.dumps({"schema_version": 1, "workflows": [
            {"id": "safe", "name": "Safe", "steps": ["audit"]}
        ]}), encoding="utf-8")
        link = self.repo / ".steadfast" / "automations.json"
        try:
            link.symlink_to(real)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks are not available on this platform")
        with self.assertRaisesRegex(ValueError, "symlink"):
            list_automations(self.repo)

    def test_history_rejects_corrupt_records(self):
        path = self.repo / ".steadfast" / "automation-runs.jsonl"
        path.write_text("{broken\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "corrupt"):
            automation_history(self.repo)


if __name__ == "__main__":
    unittest.main()
