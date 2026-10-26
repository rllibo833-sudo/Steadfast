import json
import tempfile
import unittest
from pathlib import Path

from steadfast.contracts import contract_findings, validate_policy_data
from steadfast.evidence import load_records, new_record, save_records, validate_record
from steadfast.inventory import inventory_report
from steadfast.policy import init_policy, load_policy
from steadfast.release import release_report
from steadfast.sarif import to_sarif


class ContractTests(unittest.TestCase):
    def test_policy_validator_rejects_wrong_root_and_unsafe_evidence_path(self):
        self.assertEqual(validate_policy_data([])[0]["code"], "POLICY_NOT_OBJECT")
        findings = validate_policy_data({
            "version": 1,
            "product_code_budget": 20000,
            "allowed_paths": ["src/**"],
            "documentation_paths": [],
            "required_evidence": ["../outside.md"],
            "implementation_paths": ["src/**"],
            "ignored_paths": [],
        })
        self.assertIn("POLICY_EVIDENCE_PATH_UNSAFE", [item["code"] for item in findings])

    def test_required_text_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            (repo / "README.md").write_text("# Steadfast\n", encoding="utf-8")
            findings = contract_findings(repo, {
                "required_files": ["README.md", "LICENSE"],
                "required_text": [{"path": "README.md", "contains": "install"}],
            })
            codes = {item["code"] for item in findings}
            self.assertIn("REQUIRED_FILE_MISSING", codes)
            self.assertIn("REQUIRED_TEXT_MISSING", codes)


class EvidenceTests(unittest.TestCase):
    def test_record_requires_real_command_and_timestamp(self):
        record = new_record("unit suite", "python -m unittest", 0, "passed")
        self.assertEqual(validate_record(record.to_dict()), [])
        invalid = record.to_dict()
        invalid["exit_code"] = "0"
        self.assertIn("exit_code must be an integer", validate_record(invalid))

    def test_evidence_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "evidence.json"
            record = new_record("unit suite", "python -m unittest", 0, "passed")
            save_records(path, [record.to_dict()])
            records, errors = load_records(path)
            self.assertEqual(errors, [])
            self.assertEqual(records[0]["claim"], "unit suite")


class OutputTests(unittest.TestCase):
    def test_sarif_output_contains_rule_and_result(self):
        sarif = to_sarif({
            "findings": [{
                "severity": "error", "code": "SCOPE_DENIED",
                "path": "tmp/file.py", "message": "outside allowlist",
            }]
        })
        self.assertEqual(sarif["version"], "2.1.0")
        self.assertEqual(sarif["runs"][0]["results"][0]["ruleId"], "SCOPE_DENIED")

    def test_inventory_is_deterministic_and_counts_budget(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            init_policy(repo)
            source = repo / "src"
            source.mkdir()
            (source / "main.py").write_text("answer = 42\n", encoding="utf-8")
            first = inventory_report(repo)
            second = inventory_report(repo)
            self.assertEqual(first, second)
            self.assertEqual(first["product_code_lines"], 1)
            self.assertEqual(first["implementation_file_count"], 1)

    def test_release_check_reports_missing_changelog_as_warning(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            init_policy(repo)
            (repo / "src").mkdir()
            (repo / "src" / "main.py").write_text("answer = 42\n", encoding="utf-8")
            result = release_report(repo)
            self.assertTrue(result["ready"])
            self.assertIn("CHANGELOG_NOT_READY", [item["code"] for item in result["findings"]])


    def test_release_check_blocks_secret_files_in_implementation_scope(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            init_policy(repo)
            source = repo / "src"
            source.mkdir()
            (source / "main.py").write_text("answer = 42\n", encoding="utf-8")
            (source / ".env").write_text("API_KEY=\"real-secret-value-123456\"\n", encoding="utf-8")
            result = release_report(repo)
            self.assertFalse(result["ready"])
            self.assertIn("ENV_FILE_IN_SOURCE_SCOPE", [item["code"] for item in result["findings"]])


if __name__ == "__main__":
    unittest.main()
