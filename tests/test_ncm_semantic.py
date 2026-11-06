import unittest
from unittest.mock import patch

from steadfast.ncm_semantic import infer_semantic_candidates


class NcmSemanticTests(unittest.TestCase):
    def setUp(self):
        self.manifest = {
            "universe_id": "test",
            "manifest_version": "1",
            "projects": [
                {"id": "alpha", "name": "Alpha", "purpose": "Build a shared knowledge archive."},
                {"id": "beta", "name": "Beta", "purpose": "Analyze digital evidence."},
            ],
        }

    def test_remote_transfer_requires_explicit_opt_in(self):
        result = infer_semantic_candidates(self.manifest, env={})
        self.assertEqual(result["status"], "blocked")
        self.assertFalse(result["safety"]["remote_request_made"])

    def test_unconfigured_model_fails_without_leaking_credentials(self):
        result = infer_semantic_candidates(self.manifest, allow_remote=True, env={})
        self.assertEqual(result["status"], "failed")
        self.assertNotIn("api_key", str(result).lower())

    def test_model_candidates_require_verbatim_manifest_evidence(self):
        response = {
            "concepts": [{
                "name": "Shared knowledge",
                "definition": "A reusable knowledge repository.",
                "evidence": [{"path": "projects[alpha].purpose", "quote": "shared knowledge archive"}],
            }],
            "relations": [{
                "from": "alpha", "to": "beta", "type": "supports",
                "rationale": "The projects share an evidence workflow.",
                "confidence": 0.72,
                "evidence": [{"path": "projects[alpha].purpose", "quote": "shared knowledge archive"}],
            }],
            "possible_conflicts": [],
        }
        with patch("steadfast.ncm_semantic._call_model", return_value=response):
            result = infer_semantic_candidates(self.manifest, allow_remote=True, env={"NCM_MODEL": "test"})
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["summary"]["concepts"], 1)
        self.assertEqual(result["summary"]["relations"], 1)
        self.assertEqual(result["concepts"][0]["epistemic_status"], "candidate")
        self.assertTrue(result["safety"]["evidence_quotes_verified_against_manifest"])

    def test_fabricated_evidence_is_rejected(self):
        response = {
            "concepts": [{
                "name": "Invented",
                "definition": "Not grounded.",
                "evidence": [{"path": "projects[alpha].purpose", "quote": "not in source"}],
            }],
            "relations": [],
            "possible_conflicts": [],
        }
        with patch("steadfast.ncm_semantic._call_model", return_value=response):
            result = infer_semantic_candidates(self.manifest, allow_remote=True, env={"NCM_MODEL": "test"})
        self.assertEqual(result["summary"]["concepts"], 0)
        self.assertEqual(result["findings"][0]["code"], "UNSUPPORTED_CONCEPT_EVIDENCE")


if __name__ == "__main__":
    unittest.main()
