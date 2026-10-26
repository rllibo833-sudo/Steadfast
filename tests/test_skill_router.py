from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from steadfast.skill_router import route_skills


class SkillRouterTests(unittest.TestCase):
    def test_routes_task_by_description_and_body_without_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            skill = root / "skills" / "python-debugging" / "SKILL.md"
            skill.parent.mkdir(parents=True)
            skill.write_text(
                "---\nname: python-debugging\ndescription: Debug Python exceptions and tracebacks\n---\n"
                "Inspect stack traces, reproduce the bug, and add regression tests.\n",
                encoding="utf-8",
            )
            (root / "skills" / "design").mkdir(parents=True)
            (root / "skills" / "design" / "SKILL.md").write_text(
                "---\nname: interface-design\ndescription: Design accessible user interfaces\n---\n"
                "Create layouts and responsive visual components.\n", encoding="utf-8")
            result = route_skills(root, "debug Python traceback and fix exception")
            self.assertEqual(result["status"], "matched")
            self.assertEqual(result["skills"][0]["name"], "python-debugging")
            self.assertEqual(result["execution"], "not_performed")
            self.assertIn("debug", result["skills"][0]["matched_terms"])

    def test_discovers_agent_native_skill_roots_and_is_deterministic(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            skill = root / ".agents" / "skills" / "security-review" / "SKILL.md"
            skill.parent.mkdir(parents=True)
            skill.write_text("---\nname: security-review\ndescription: Security vulnerability review\n---\n"
                             "Audit injection and permission boundaries.\n", encoding="utf-8")
            first = route_skills(root, "security vulnerability injection")
            second = route_skills(root, "security vulnerability injection")
            self.assertEqual(first, second)
            self.assertEqual(first["skills"][0]["path"], ".agents/skills/security-review/SKILL.md")

    def test_empty_task_and_invalid_limit_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                route_skills(Path(directory), " ")
            with self.assertRaises(ValueError):
                route_skills(Path(directory), "test", limit=0)

    def test_no_match_is_explicit(self):
        with tempfile.TemporaryDirectory() as directory:
            result = route_skills(Path(directory), "quantum telescope astrophysics")
            self.assertEqual(result["status"], "no_match")
            self.assertEqual(result["skills"], [])


if __name__ == "__main__":
    unittest.main()
