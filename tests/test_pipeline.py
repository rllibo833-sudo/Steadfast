import json
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

from steadfast.pipeline import PipelineError, load_pipeline, run_pipeline


class PipelineManifestTests(unittest.TestCase):
    def write_manifest(self, root: Path, data: object) -> Path:
        path = root / ".steadfast" / "pipeline.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    def test_rejects_unknown_dependency_and_cycles(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = self.write_manifest(root, {
                "version": 1,
                "steps": [{"id": "one", "command": ["python", "-V"], "depends_on": ["missing"]}],
            })
            with self.assertRaisesRegex(PipelineError, "unknown step"):
                load_pipeline(path)
            path = self.write_manifest(root, {
                "version": 1,
                "steps": [
                    {"id": "one", "command": ["python", "-V"], "depends_on": ["two"]},
                    {"id": "two", "command": ["python", "-V"], "depends_on": ["one"]},
                ],
            })
            with self.assertRaisesRegex(PipelineError, "cycle"):
                load_pipeline(path)

    def test_rejects_shell_string_and_unsafe_cwd(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.write_manifest(root, {
                "version": 1,
                "steps": [{"id": "bad", "command": "echo unsafe", "cwd": "../outside"}],
            })
            with self.assertRaisesRegex(PipelineError, "command"):
                load_pipeline(root / ".steadfast" / "pipeline.json")
            self.write_manifest(root, {
                "version": 1,
                "steps": [{"id": "bad", "command": ["python", "-V"], "cwd": "../outside"}],
            })
            with self.assertRaisesRegex(PipelineError, "repository-relative"):
                run_pipeline(root)

    def test_executes_steps_and_skips_failed_dependencies(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.write_manifest(root, {
                "version": 1,
                "steps": [
                    {"id": "fail", "command": [sys.executable, "-c", "raise SystemExit(7)"]},
                    {"id": "blocked", "command": [sys.executable, "-c", "print('should not run')"],
                     "depends_on": ["fail"]},
                    {"id": "independent", "command": [sys.executable, "-c", "print('works')"]},
                ],
            })
            result = run_pipeline(root)
            self.assertFalse(result["passed"])
            self.assertEqual([item["status"] for item in result["steps"]],
                             ["failed", "skipped", "passed"])
            self.assertEqual(result["steps"][0]["exit_code"], 7)
            self.assertIn("works", result["steps"][2]["stdout"])

    def test_timeout_is_reported_without_hanging_the_pipeline(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.write_manifest(root, {
                "version": 1,
                "steps": [{"id": "slow", "command": [
                    sys.executable, "-c", "import time; time.sleep(2)"
                ], "timeout": 1}],
            })
            result = run_pipeline(root)
            self.assertEqual(result["steps"][0]["status"], "timed_out")
            self.assertFalse(result["passed"])

    def test_unlisted_host_secrets_are_not_inherited(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.write_manifest(root, {
                "version": 1,
                "steps": [{"id": "secret", "command": [
                    sys.executable, "-c",
                    'import os; print(os.getenv("STEADFAST_HOST_SECRET", "absent"))'
                ]}],
            })
            with mock.patch.dict("os.environ", {"STEADFAST_HOST_SECRET": "host-secret-value"}):
                result = run_pipeline(root)
            self.assertEqual(result["steps"][0]["stdout"].strip(), "absent")
    def test_env_values_are_redacted_from_captured_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.write_manifest(root, {
                "version": 1,
                "steps": [{"id": "secret", "command": [
                    sys.executable, "-c", "import os; print(os.environ['DEMO_TOKEN'])"
                ], "env": {"DEMO_TOKEN": "sensitive-value-123"}}],
            })
            result = run_pipeline(root)
            self.assertNotIn("sensitive-value-123", result["steps"][0]["stdout"])
            self.assertIn("[REDACTED]", result["steps"][0]["stdout"])


if __name__ == "__main__":
    unittest.main()
