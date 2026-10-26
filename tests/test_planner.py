from __future__ import annotations
import tempfile
import unittest
from pathlib import Path
from steadfast.policy import init_policy
from steadfast.planner import execution_plan, explain_goal

class ExecutionPlannerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        init_policy(self.repo)
        goals = self.repo / ".steadfast" / "goals"
        goals.mkdir(parents=True, exist_ok=True)
        (goals / "base.md").write_text(
            "---\nid: base\ntitle: Base runtime\nstatus: done\ndepends_on: []\n---\n"
            "## Acceptance criteria\n- [x] Runtime loads\n", encoding="utf-8")
        (goals / "security.md").write_text(
            "---\nid: security\ntitle: Security hardening\nstatus: ready\ndepends_on: [base]\n---\n"
            "## Acceptance criteria\n- [ ] Validate input\n- [ ] Reject unsafe path\n", encoding="utf-8")
        (goals / "release.md").write_text(
            "---\nid: release\ntitle: Release packaging\nstatus: ready\ndepends_on: [security]\n---\n"
            "## Acceptance criteria\n- [ ] Package installs\n", encoding="utf-8")
        (goals / "idea.md").write_text(
            "---\nid: idea\ntitle: Future integration\nstatus: proposed\ndepends_on: []\n---\n"
            "## Acceptance criteria\n- [ ] Prototype integration\n", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_only_ready_dependency_satisfied_goals_enter_queue(self):
        plan = execution_plan(self.repo)
        self.assertEqual(plan["ready_count"], 1)
        self.assertEqual(plan["execution_queue"][0]["goal_id"], "security")
        blocked = {item["goal_id"]: item for item in plan["blocked_or_unready"]}
        self.assertIn("waiting for security", blocked["release"]["waiting_reasons"][0])
        self.assertNotIn("idea", blocked)

    def test_proposed_goals_are_opt_in(self):
        default = execution_plan(self.repo)
        expanded = execution_plan(self.repo, include_proposed=True)
        self.assertNotIn("idea", [x["goal_id"] for x in default["blocked_or_unready"]])
        self.assertIn("idea", [x["goal_id"] for x in expanded["blocked_or_unready"]])

    def test_explain_goal_includes_criteria_and_dependencies(self):
        detail = explain_goal(self.repo, "security")
        self.assertEqual(detail["acceptance_criteria"], ["Validate input", "Reject unsafe path"])
        self.assertEqual(detail["dependencies"][0]["id"], "base")
        self.assertTrue(detail["plan_item"]["ready"])

    def test_missing_dependency_is_reported_and_never_ready(self):
        path = self.repo / ".steadfast" / "goals" / "security.md"
        path.write_text(path.read_text(encoding="utf-8").replace("[base]", "[missing]"), encoding="utf-8")
        plan = execution_plan(self.repo)
        self.assertTrue(any("missing goal missing" in error for error in plan["graph_errors"]))
        item = next(x for x in plan["blocked_or_unready"] if x["goal_id"] == "security")
        self.assertFalse(item["ready"])

    def test_dependency_cycle_is_reported(self):
        path = self.repo / ".steadfast" / "goals" / "base.md"
        path.write_text(path.read_text(encoding="utf-8").replace("status: done", "status: done").replace("depends_on: []", "depends_on: [release]"), encoding="utf-8")
        plan = execution_plan(self.repo)
        self.assertTrue(any("dependency cycle" in error for error in plan["graph_errors"]))

if __name__ == "__main__":
    unittest.main()
