from __future__ import annotations

import json
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from steadfast.policy import init_policy
from steadfast.workorders import (
    WorkOrderError,
    active_work_order,
    close_work_order,
    issue_work_order,
    matches_work_order_scope,
    show_work_order,
    verify_work_order,
    _now,
    _write_order,
)


class WorkOrderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.repo = Path(self.temp.name)
        init_policy(self.repo)
        (self.repo / ".steadfast" / "goal.md").write_text(
            "# Product goal\n\n## Acceptance criteria\n- [ ] Change is reviewed\n- [ ] Verification passes\n",
            encoding="utf-8",
        )
        (self.repo / "src").mkdir()
        (self.repo / "src" / "module.py").write_text("VALUE = 1\n", encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def test_issue_verify_and_close_work_order(self):
        order = issue_work_order(self.repo, "goal", owner="agent-a", ttl_minutes=60)
        self.assertEqual(order["status"], "issued")
        self.assertEqual(len(order["acceptance"]), 2)
        self.assertEqual(active_work_order(self.repo)["id"], order["id"])
        pipeline = {"tool": "steadfast", "passed": True, "summary": {}, "steps": [],
                    "manifest": ".steadfast/pipeline.json", "duration_seconds": 0.1}
        with patch("steadfast.workorders.run_pipeline", return_value=pipeline):
            with patch("steadfast.workorders.record_run", return_value={"run_id": "run-1"}):
                verified = verify_work_order(self.repo, order["id"])
        self.assertTrue(verified["passed"])
        self.assertEqual(show_work_order(self.repo, order["id"])["status"], "verified")
        closed = close_work_order(self.repo, order["id"])
        self.assertEqual(closed["status"], "closed")
        self.assertIsNone(active_work_order(self.repo))

    def test_out_of_scope_changes_fail_work_order_verification(self):
        order = issue_work_order(
            self.repo, "goal", scope_paths=["src/**"], ttl_minutes=60
        )
        (self.repo / "outside.txt").write_text("not in this task\n", encoding="utf-8")
        pipeline = {"tool": "steadfast", "passed": True, "summary": {}, "steps": [],
                    "manifest": ".steadfast/pipeline.json", "duration_seconds": 0.1}
        with patch("steadfast.workorders.run_pipeline", return_value=pipeline):
            with patch("steadfast.workorders.record_run", return_value={"run_id": "run-2"}):
                result = verify_work_order(self.repo, order["id"])
        self.assertFalse(result["passed"])
        self.assertIn("outside.txt", result["changed_paths"])
        self.assertTrue(any(item["code"] == "WORK_ORDER_SCOPE_ESCAPE" for item in result["scope"]["findings"]))

    def test_scope_cannot_expand_global_policy(self):
        with self.assertRaisesRegex(WorkOrderError, "expand beyond policy"):
            issue_work_order(self.repo, "goal", scope_paths=["outside/**"])

    def test_work_order_hash_detects_tampering(self):
        order = issue_work_order(self.repo, "goal")
        path = self.repo / ".steadfast" / "work-orders" / (order["id"] + ".json")
        data = json.loads(path.read_text(encoding="utf-8"))
        data["owner"] = "attacker"
        path.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(WorkOrderError, "integrity"):
            show_work_order(self.repo, order["id"])

    def test_scope_match_supports_exact_paths_and_directory_prefixes(self):
        self.assertTrue(matches_work_order_scope("src/module.py", ["src/**"]))
        self.assertTrue(matches_work_order_scope("README.md", ["README.md"]))
        self.assertFalse(matches_work_order_scope("outside.txt", ["src/**"]))

    def test_only_one_active_work_order_is_allowed(self):
        issue_work_order(self.repo, "goal")
        with self.assertRaisesRegex(WorkOrderError, "active work order"):
            issue_work_order(self.repo, "goal")



    def test_goal_acceptance_change_invalidates_work_order(self):
        order = issue_work_order(self.repo, "goal")
        goal = self.repo / ".steadfast" / "goal.md"
        goal.write_text(
            "# Product goal\n\n## Acceptance criteria\n- [ ] Different criterion\n",
            encoding="utf-8",
        )
        pipeline = {"tool": "steadfast", "passed": True, "summary": {}, "steps": [],
                    "manifest": ".steadfast/pipeline.json", "duration_seconds": 0.1}
        with patch("steadfast.workorders.run_pipeline", return_value=pipeline):
            with patch("steadfast.workorders.record_run", return_value={"run_id": "run-3"}):
                result = verify_work_order(self.repo, order["id"])
        self.assertFalse(result["passed"])
        self.assertFalse(result["goal_unchanged"])
        self.assertIn("WORK_ORDER_GOAL_CHANGED", [item["code"] for item in result["scope"]["findings"]])


if __name__ == "__main__":
    unittest.main()
