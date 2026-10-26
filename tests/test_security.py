import tempfile
import unittest
from pathlib import Path

from steadfast.policy import init_policy, load_policy
from steadfast.security import security_findings, workflow_findings


class SecurityScannerTests(unittest.TestCase):
    def test_secret_is_detected_but_value_is_not_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            init_policy(repo)
            source = repo / "src"
            source.mkdir()
            secret = "sk_live_this_is_a_fake_secret_123"
            (source / "settings.py").write_text(
                f'api_key = "{secret}"\n', encoding="utf-8"
            )
            findings = security_findings(repo, load_policy(repo))
            self.assertIn("POSSIBLE_HARDCODED_SECRET", [item["code"] for item in findings])
            self.assertNotIn(secret, str(findings))

    def test_risky_api_patterns_are_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            init_policy(repo)
            source = repo / "src"
            source.mkdir()
            (source / "unsafe.py").write_text(
                "import requests\nrequests.get(url, verify=False)\n"
                "import tempfile\ntempfile.mktemp()\n"
                "import pickle\npickle.loads(data)\n",
                encoding="utf-8",
            )
            codes = {item["code"] for item in security_findings(repo, load_policy(repo))}
            self.assertTrue({"TLS_VERIFY_DISABLED", "INSECURE_TEMPFILE", "UNTRUSTED_PICKLE_REVIEW"} <= codes)

    def test_workflow_event_interpolation_is_an_error(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            workflow = repo / ".github" / "workflows"
            workflow.mkdir(parents=True)
            (workflow / "comment.yml").write_text(
                'name: Comment\non: issue_comment\njobs:\n  build:\n'
                '    steps:\n      - run: echo "${{ github.event.comment.body }}"\n',
                encoding="utf-8",
            )
            findings = workflow_findings(repo)
            self.assertIn("UNTRUSTED_EVENT_SHELL_INTERPOLATION", [item["code"] for item in findings])

    def test_workflow_action_tags_are_warned(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            workflow = repo / ".github" / "workflows"
            workflow.mkdir(parents=True)
            (workflow / "ci.yml").write_text(
                "name: CI\npermissions:\n  contents: read\njobs:\n"
                "  build:\n    steps:\n      - uses: actions/checkout@v4\n",
                encoding="utf-8",
            )
            findings = workflow_findings(repo)
            self.assertIn("ACTION_TAG_NOT_PINNED", [item["code"] for item in findings])


if __name__ == "__main__":
    unittest.main()
