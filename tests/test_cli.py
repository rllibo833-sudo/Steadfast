import tempfile
import unittest
from pathlib import Path

from steadfast.cli import main


class CliTests(unittest.TestCase):
    def test_init_and_evidence_check(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(main(["--repo", directory, "init"]), 0)
            self.assertEqual(main(["--repo", directory, "evidence-check"]), 0)

    def test_security_check_has_a_dedicated_dispatch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".steadfast").mkdir()
            (root / ".steadfast" / "policy.json").write_text(
                '{"version":1,"product_code_budget":20000,"allowed_paths":["src/**"],'
                '"implementation_paths":["src/**"],"ignored_paths":[],"required_evidence":[]}',
                encoding="utf-8",
            )
            (root / "src").mkdir()
            (root / "src" / "safe.py").write_text("value = 1\\n", encoding="utf-8")
            self.assertEqual(main(["--repo", directory, "security-check"]), 0)

    def test_plan_command_runs_without_configured_goal_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(main(["--repo", directory, "init"]), 0)
            self.assertEqual(main(["--repo", directory, "plan"]), 0)


    def test_discover_emits_machine_readable_capability_map(self):
        import contextlib
        import io
        import json

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.assertEqual(main(["--repo", directory, "init"]), 0)
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(main(["--repo", directory, "discover"]), 0)
            report = json.loads(output.getvalue())
            self.assertEqual(report["schema_version"], 1)
            self.assertIn("policy", report["entrypoints"])
            self.assertFalse(report["cost_policy"]["paid_runner_required"])
            self.assertEqual(report["supported_integrations"], ["claude", "cursor", "codex"])

    def test_onboard_sets_up_foundation_and_preserves_existing_agent_instructions(self):
        import contextlib
        import io
        import json

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "AGENTS.md").write_text("maintainer-owned instructions\\n", encoding="utf-8")
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(main(["--repo", directory, "onboard", "--agent", "codex"]), 0)
            result = json.loads(output.getvalue())
            self.assertEqual(result["status"], "ready")
            self.assertTrue((root / ".steadfast" / "policy.json").is_file())
            self.assertTrue((root / ".agents" / "skills" / "steadfast-governance" / "SKILL.md").is_file())
            self.assertEqual((root / "AGENTS.md").read_text(encoding="utf-8"), "maintainer-owned instructions\\n")
            self.assertIn("AGENTS.md", result["preserved_existing_files"])
            self.assertFalse(result["external_registration_required"])

    def test_python_module_entrypoint_exists(self):
        self.assertTrue(
            (Path(__file__).parents[1] / "src" / "steadfast" / "__main__.py").is_file()
        )


if __name__ == "__main__":
    unittest.main()
