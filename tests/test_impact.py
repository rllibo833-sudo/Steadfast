from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from steadfast.impact import analyze_change_impact
from steadfast.policy import init_policy


class ChangeImpactTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.repo = Path(self.temp.name)
        init_policy(self.repo)
        (self.repo / "src" / "steadfast").mkdir(parents=True)
        (self.repo / "tests").mkdir()
        (self.repo / "src" / "steadfast" / "cli.py").write_text("def main():\n    return 0\n", encoding="utf-8")
        (self.repo / "tests" / "test_cli.py").write_text("def test_main():\n    assert True\n", encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def test_classifies_source_tests_and_recommends_review_gates(self):
        report = analyze_change_impact(
            self.repo,
            paths=["src/steadfast/cli.py", "tests/test_cli.py"],
        )
        self.assertTrue(report["passed"])
        self.assertEqual(report["classification_counts"]["source"], 1)
        self.assertEqual(report["classification_counts"]["test"], 1)
        self.assertIn("regression-review", report["required_gates"])
        self.assertFalse(report["missing_test_links"])

    def test_source_without_changed_test_is_reported_as_warning(self):
        report = analyze_change_impact(self.repo, paths=["src/steadfast/cli.py"])
        self.assertTrue(report["passed"])
        self.assertEqual(report["missing_test_links"][0]["source"], "src/steadfast/cli.py")
        self.assertIn("IMPACT_SOURCE_WITHOUT_CHANGED_TEST", [item["code"] for item in report["findings"]])

    def test_sensitive_paths_block_review_pass(self):
        report = analyze_change_impact(self.repo, paths=[".env.production"])
        self.assertFalse(report["passed"])
        self.assertEqual(report["findings"][0]["code"], "IMPACT_SENSITIVE_PATH")
        self.assertIn("human-review", report["required_gates"])

    def test_parent_traversal_is_rejected(self):
        report = analyze_change_impact(self.repo, paths=["../outside.py"])
        self.assertFalse(report["passed"])
        self.assertEqual(report["findings"][0]["code"], "IMPACT_PATH_INVALID")

    def test_non_git_workspace_requires_explicit_paths(self):
        report = analyze_change_impact(self.repo)
        self.assertFalse(report["passed"])
        self.assertEqual(report["findings"][0]["code"], "IMPACT_GIT_UNAVAILABLE")


if __name__ == "__main__":
    unittest.main()
