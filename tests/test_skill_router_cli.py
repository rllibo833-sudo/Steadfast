from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from steadfast.cli import main


class SkillRouterCliTests(unittest.TestCase):
    def test_cli_returns_ranked_skill_candidates(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            skill = root / "skills" / "testing" / "SKILL.md"
            skill.parent.mkdir(parents=True)
            skill.write_text("---\nname: test-writing\ndescription: Write unit tests and regression tests\n---\n"
                             "Use pytest to verify behavior and reproduce bugs.\n", encoding="utf-8")
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = main(["--repo", directory, "skills", "route", "write unit tests", "--limit", "3"])
            report = json.loads(output.getvalue())
            self.assertEqual(code, 0)
            self.assertEqual(report["skills"][0]["name"], "test-writing")

    def test_cli_returns_nonzero_when_no_skill_matches(self):
        with tempfile.TemporaryDirectory() as directory:
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = main(["--repo", directory, "skills", "route", "quantum astrophysics"])
            self.assertEqual(code, 1)
            self.assertEqual(json.loads(output.getvalue())["status"], "no_match")


if __name__ == "__main__":
    unittest.main()
