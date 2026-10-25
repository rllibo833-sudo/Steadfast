import tempfile
import unittest
from pathlib import Path
from steadfast.policy import init_policy, load_policy
from steadfast.checks import scope_findings, product_code_lines

class PolicyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        init_policy(self.repo)
        self.policy = load_policy(self.repo)
        (self.repo / ".git").mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def test_init_is_non_destructive(self):
        path = self.repo / ".steadfast" / "goal.md"
        path.write_text("custom goal", encoding="utf-8")
        init_policy(self.repo)
        self.assertEqual(path.read_text(), "custom goal")

    def test_outside_scope_is_error(self):
        findings = scope_findings(self.repo, self.policy, ["src/app.py", "random/new_feature.py"])
        self.assertEqual([f["path"] for f in findings], ["random/new_feature.py"])

    def test_budget_counts_implementation_lines(self):
        src = self.repo / "src"
        src.mkdir()
        (src / "app.py").write_text("x = 1\n\n# comment\ny = 2\n", encoding="utf-8")
        total, _ = product_code_lines(self.repo, self.policy)
        self.assertEqual(total, 2)

if __name__ == "__main__":
    unittest.main()
