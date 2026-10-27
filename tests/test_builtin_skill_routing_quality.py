from __future__ import annotations

import unittest
from pathlib import Path

from steadfast.skill_router import route_skills


class BuiltInSkillRoutingQualityTests(unittest.TestCase):
    """Regression cases for choosing a specialized skill from real task wording."""

    REPO_ROOT = Path(__file__).resolve().parents[1]

    CASES = (
        (
            "CI is red after a commit. Find the first causal error in the job logs, "
            "reproduce it, patch the root cause, and add a regression test.",
            "ci-failure-autopsy",
        ),
        (
            "Review a GitHub Actions pull_request_target workflow for fork-controlled "
            "code reaching a write token or deployment secret.",
            "actions-supply-chain-review",
        ),
        (
            "The published Python wheel installs but the CLI crashes with "
            "ModuleNotFoundError. Inspect wheel and sdist contents in a clean venv.",
            "python-release-breakage",
        ),
    )

    def test_realistic_tasks_route_to_the_expected_specialist(self):
        for task, expected_name in self.CASES:
            with self.subTest(expected_skill=expected_name):
                result = route_skills(self.REPO_ROOT, task, limit=5)
                self.assertEqual(result["status"], "matched")
                self.assertTrue(result["skills"], "router returned no candidates")
                self.assertEqual(
                    result["skills"][0]["name"],
                    expected_name,
                    msg=f"Task routed to {result['skills'][0]['name']!r}; "
                    f"ranked candidates: {[item['name'] for item in result['skills']]}",
                )

    def test_new_specialist_skills_have_actionable_descriptions(self):
        expected = {
            "ci-failure-autopsy": ("CI", "reproduce", "regression"),
            "actions-supply-chain-review": ("GitHub Actions", "untrusted", "token"),
            "python-release-breakage": ("Python", "wheel", "sdist"),
        }
        for name, required_terms in expected.items():
            with self.subTest(skill=name):
                path = self.REPO_ROOT / "skills" / name / "SKILL.md"
                self.assertTrue(path.is_file(), f"missing specialist skill: {name}")
                source = path.read_text(encoding="utf-8").casefold()
                for term in required_terms:
                    self.assertIn(term.casefold(), source, f"{name} missing {term!r}")


if __name__ == "__main__":
    unittest.main()
