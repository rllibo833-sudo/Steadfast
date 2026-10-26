import tempfile
import unittest
from pathlib import Path

from steadfast.baseline import compare_baseline, write_baseline
from steadfast.docsync import cli_commands, docs_sync_report
from steadfast.goals import goal_report
from steadfast.policy import init_policy, load_policy


class GoalGraphTests(unittest.TestCase):
    def test_missing_dependency_and_cycle_are_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            init_policy(repo)
            goals = repo / ".steadfast" / "goals"
            goals.mkdir()
            (goals / "alpha.md").write_text(
                "---\nid: alpha\ntitle: Alpha\nstatus: active\ndepends_on: beta\n---\n"
                "## Acceptance criteria\n- [ ] Done\n",
                encoding="utf-8",
            )
            (goals / "beta.md").write_text(
                "---\nid: beta\ntitle: Beta\nstatus: ready\ndepends_on: alpha\n---\n"
                "## Acceptance criteria\n- [ ] Done\n",
                encoding="utf-8",
            )
            result = goal_report(repo, load_policy(repo))
            codes = [item["code"] for item in result["findings"]]
            self.assertIn("GOAL_DEPENDENCY_CYCLE", codes)
            self.assertIn("GOAL_DEPENDENCY_NOT_DONE", codes)
            self.assertEqual(result["summary"]["total"], 2)

    def test_active_goal_limit_is_enforced(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            init_policy(repo)
            goals = repo / ".steadfast" / "goals"
            goals.mkdir()
            for name in ("alpha", "beta"):
                (goals / f"{name}.md").write_text(
                    f"---\nid: {name}\ntitle: {name}\nstatus: active\n---\n"
                    "## Acceptance criteria\n- [ ] Complete\n",
                    encoding="utf-8",
                )
            policy = load_policy(repo)
            policy["max_active_goals"] = 1
            result = goal_report(repo, policy)
            self.assertIn("ACTIVE_GOAL_LIMIT_EXCEEDED", [item["code"] for item in result["findings"]])


class BaselineTests(unittest.TestCase):
    def test_baseline_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            init_policy(repo)
            (repo / "src").mkdir()
            (repo / "src" / "module.py").write_text("value = 1\n", encoding="utf-8")
            write_baseline(repo)
            result = compare_baseline(repo)
            self.assertTrue(result["ready"])
            self.assertEqual(result["added_findings"], [])

    def test_missing_baseline_is_explicit(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            init_policy(repo)
            result = compare_baseline(repo)
            self.assertEqual(result["findings"][0]["code"], "BASELINE_MISSING")


class DocumentationSyncTests(unittest.TestCase):
    def test_command_parser_finds_subcommands(self):
        self.assertEqual(
            cli_commands('commands.add_parser("audit")\ncommands.add_parser("docs-check")'),
            ["audit", "docs-check"],
        )

    def test_docs_sync_reports_missing_package_entrypoint(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            (repo / "src" / "steadfast").mkdir(parents=True)
            (repo / "src" / "steadfast" / "cli.py").write_text(
                'commands.add_parser("audit")\n', encoding="utf-8"
            )
            (repo / "README.md").write_text("steadfast audit\n", encoding="utf-8")
            (repo / "pyproject.toml").write_text("", encoding="utf-8")
            result = docs_sync_report(repo)
            codes = [item["code"] for item in result["findings"]]
            self.assertIn("CLI_ENTRYPOINT_MISSING", codes)
            self.assertIn("MODULE_ENTRYPOINT_MISSING", codes)


if __name__ == "__main__":
    unittest.main()
