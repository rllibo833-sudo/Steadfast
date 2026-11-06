import unittest

from steadfast.ncm_inference import infer_candidate_relations


class NcmInferenceTests(unittest.TestCase):
    def setUp(self):
        self.manifest = {
            "universe_id": "test",
            "manifest_version": "1",
            "projects": [
                {"id": "beta", "purpose": "digital forensics cyber defense knowledge"},
                {"id": "alpha", "purpose": "cyber defense knowledge archive"},
                {"id": "gamma", "purpose": "solar system orbital simulation"},
            ],
        }

    def test_candidates_are_deterministic_and_evidence_backed(self):
        first = infer_candidate_relations(self.manifest, threshold=0.2)
        second = infer_candidate_relations(self.manifest, threshold=0.2)
        self.assertEqual(first, second)
        self.assertEqual(len(first["edges"]), 1)
        edge = first["edges"][0]
        self.assertEqual(edge["epistemic_status"], "candidate")
        self.assertIn("projects[alpha].purpose", edge["evidence"])
        self.assertIn("projects[beta].purpose", edge["evidence"])
        self.assertEqual(edge["attributes"]["shared_terms"], ["cyber", "defense", "knowledge"])

    def test_candidate_never_claims_semantic_understanding_or_verification(self):
        result = infer_candidate_relations(self.manifest)
        self.assertTrue(result["semantics"]["inference_performed"])
        self.assertFalse(result["semantics"]["semantic_understanding"])
        self.assertFalse(result["semantics"]["relationships_are_verified"])
        self.assertTrue(all(edge["epistemic_status"] == "candidate" for edge in result["edges"]))

    def test_threshold_filters_weak_overlap(self):
        result = infer_candidate_relations(self.manifest, threshold=0.9)
        self.assertEqual(result["edges"], [])

    def test_invalid_threshold_is_rejected(self):
        with self.assertRaises(ValueError):
            infer_candidate_relations(self.manifest, threshold=1.1)

    def test_empty_or_missing_purpose_is_ignored(self):
        result = infer_candidate_relations({"projects": [{"id": "x", "purpose": ""}]})
        self.assertEqual(result["summary"]["projects"], 0)
        self.assertEqual(result["edges"], [])


if __name__ == "__main__":
    unittest.main()
