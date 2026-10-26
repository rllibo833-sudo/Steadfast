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
