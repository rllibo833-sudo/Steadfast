import tempfile
import unittest
from pathlib import Path

from steadfast.checks import (
    documentation_findings, evidence_findings, product_code_lines, scope_findings,
)
from steadfast.policy import init_policy, load_policy


class PolicyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        init_policy(self.repo)
        self.policy = load_policy(self.repo)
        (self.repo / ".git").mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def test_init_rejects_symlinked_governance_directory(self):
        with tempfile.TemporaryDirectory() as outside:
            repo = self.repo / "symlink-test"
            repo.mkdir()
            linked = repo / ".steadfast"
            linked.symlink_to(Path(outside), target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "may not be a symlink"):
                init_policy(repo)
            self.assertEqual(list(Path(outside).iterdir()), [])
    def test_init_is_non_destructive(self):
        path = self.repo / ".steadfast" / "goal.md"
        path.write_text("custom goal", encoding="utf-8")
        init_policy(self.repo)
        self.assertEqual(path.read_text(), "custom goal")

    def test_outside_scope_is_error(self):
        findings = scope_findings(
            self.repo, self.policy, ["src/app.py", "random/new_feature.py"]
        )
        self.assertEqual([f["path"] for f in findings], ["random/new_feature.py"])

    def test_parent_traversal_is_rejected_even_if_allowlisted(self):
        self.policy["allowed_paths"].append("../outside.py")
        findings = scope_findings(self.repo, self.policy, ["../outside.py"])
        self.assertEqual(findings[0]["code"], "INVALID_REPOSITORY_PATH")

    def test_budget_counts_nonblank_noncomment_implementation_lines(self):
        src = self.repo / "src"
        src.mkdir()
        (src / "app.py").write_text("x = 1\n\n# comment\ny = 2\n", encoding="utf-8")
        total, files = product_code_lines(self.repo, self.policy)
        self.assertEqual(total, 2)
        self.assertEqual(files, ["src/app.py"])

    def test_budget_excludes_generated_metadata_and_non_code_files(self):
        src = self.repo / "src"
        src.mkdir()
        metadata = src / "package.egg-info"
        metadata.mkdir()
        (metadata / "entry_points.txt").write_text("steadfast = package.cli:main\n", encoding="utf-8")
        (src / "manifest.json").write_text('{"generated": true}\n', encoding="utf-8")
        (src / "real.py").write_text("def run():\n    return True\n", encoding="utf-8")
        total, files = product_code_lines(self.repo, self.policy)
        self.assertEqual(total, 2)
        self.assertEqual(files, ["src/real.py"])

    def test_docs_drift_warning_only_when_implementation_changes_alone(self):
        self.assertEqual(
            documentation_findings(self.policy, ["src/app.py"])[0]["code"],
            "DOCS_NOT_CHANGED",
        )
        self.assertEqual(
            documentation_findings(self.policy, ["src/app.py", "README.md"]), []
        )

    def test_missing_evidence_is_reported(self):
        findings = evidence_findings(
            self.repo, {"required_evidence": ["evidence/missing.md"]}
        )
        self.assertEqual(findings[0]["code"], "EVIDENCE_MISSING")


if __name__ == "__main__":
    unittest.main()
