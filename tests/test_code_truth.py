from __future__ import annotations
import tempfile
import unittest
from pathlib import Path
from steadfast.code_truth import _example_findings, _source_facts, code_truth_report
from steadfast.policy import init_policy, load_policy

class CodeTruthTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.repo = Path(self.temp.name)
        init_policy(self.repo)
        (self.repo / "src" / "steadfast").mkdir(parents=True, exist_ok=True)
        (self.repo / "tests").mkdir(exist_ok=True)
        (self.repo / "src" / "steadfast" / "cli.py").write_text(
            'import argparse\ndef parser():\n root=argparse.ArgumentParser()\n sub=root.add_subparsers(dest="command")\n sub.add_parser("audit")\n cycle=sub.add_parser("cycle")\n c=cycle.add_subparsers(dest="action")\n c.add_parser("start")\n return root\n', encoding="utf-8")
        (self.repo / "src" / "steadfast" / "__main__.py").write_text("from .cli import main\n", encoding="utf-8")
        (self.repo / "src" / "steadfast" / "__init__.py").write_text("__version__='test'\n", encoding="utf-8")
        (self.repo / "pyproject.toml").write_text('[project.scripts]\nsteadfast = "steadfast.cli:main"\n', encoding="utf-8")
        (self.repo / "README.md").write_text(
            "Examples:\n\n```sh\nsteadfast audit\nsteadfast cycle start goal\n```\n", encoding="utf-8")
        (self.repo / "tests" / "test_sample.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def test_valid_documented_command_paths(self):
        findings, count = _example_findings(self.repo, ["audit", "cycle"], {"audit": [], "cycle": ["start"]})
        self.assertEqual(findings, [])
        self.assertEqual(count, 2)

    def test_stale_command_is_flagged_against_runtime_commands(self):
        (self.repo / "README.md").write_text("steadfast deploy-now --force\n", encoding="utf-8")
        findings, _ = _example_findings(self.repo, ["audit"], {"audit": []})
        self.assertEqual(findings[0]["code"], "DOC_COMMAND_NOT_IN_CODE")

    def test_stale_subcommand_is_flagged(self):
        (self.repo / "README.md").write_text("steadfast cycle deploy\n", encoding="utf-8")
        findings, _ = _example_findings(self.repo, ["cycle"], {"cycle": ["start"]})
        self.assertEqual(findings[0]["code"], "DOC_SUBCOMMAND_NOT_IN_CODE")

    def test_product_facts_derive_from_source_and_tests(self):
        facts = _source_facts(self.repo, load_policy(self.repo))
        self.assertGreaterEqual(facts["implementation"]["files"], 3)
        self.assertGreater(facts["implementation"]["nonblank_noncomment_lines"], 0)
        self.assertEqual(facts["tests"]["files"], 1)
        self.assertGreater(facts["tests"]["nonblank_noncomment_lines"], 0)

    def test_report_hashes_source_and_checks_entrypoints(self):
        result = code_truth_report(self.repo)
        self.assertIn("src/steadfast/cli.py", result["source_sha256"])
        self.assertTrue(result["entrypoints"]["console_script_valid"])
        self.assertTrue(result["entrypoints"]["module_entrypoint_exists"])
        self.assertIn("runtime argparse parser", result["source_of_truth"])

if __name__ == "__main__":
    unittest.main()
