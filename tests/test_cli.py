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

    def test_python_module_entrypoint_exists(self):
        self.assertTrue(
            (Path(__file__).parents[1] / "src" / "steadfast" / "__main__.py").is_file()
        )


if __name__ == "__main__":
    unittest.main()
