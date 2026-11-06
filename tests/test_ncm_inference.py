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

    def test_extraction_and_candidates_are_deterministic(self):
        first = infer_candidate_relations(self.manifest, threshold=0.2)
        self.assertEqual(first, infer_candidate_relations(self.manifest, threshold=0.2))
        self.assertGreater(first["summary"]["candidate_concepts"], 0)
        self.assertEqual(first["summary"]["candidate_relations"], 1)
        self.assertTrue(any(node["kind"] == "candidate_concept" for node in first["nodes"]))

    def test_candidate_edges_have_exact_source_spans(self):
        result = infer_candidate_relations(self.manifest)
        mention_edges = [edge for edge in result["edges"] if edge["type"] == "mentions_candidate_concept"]
        self.assertTrue(mention_edges)
        self.assertTrue(all(":".join(edge["evidence"].split(":")[-2:]).count(":") == 1 for edge in mention_edges))
        self.assertTrue(all(edge["epistemic_status"] == "candidate" for edge in mention_edges))

    def test_candidate_relation_has_reconciliation_note(self):
        manifest = dict(self.manifest)
        manifest["relationships"] = [{"from": "alpha", "to": "beta", "type": "related", "status": "proposed"}]
        result = infer_candidate_relations(manifest)
        item = result["review_queue"][0]
        self.assertEqual(item["reconciliation"], "declared_pair_exists")
        self.assertTrue(item["review_required"])

    def test_absent_declared_pair_is_not_called_a_conflict(self):
        result = infer_candidate_relations(self.manifest)
        self.assertEqual(result["review_queue"][0]["reconciliation"], "no_matching_declared_pair")
        self.assertIn("not evidence of contradiction", result["review_queue"][0]["note"])

    def test_character_spans_preserve_original_unicode_text(self):
        manifest = {"projects": [{"id": "unicode", "purpose": "Pemrosesan data — café dan analisis"}]}
        result = infer_candidate_relations(manifest)
        project_edge = next(edge for edge in result["edges"] if edge["type"] == "mentions_candidate_concept")
        _, start, end = project_edge["evidence"].split(":")
        self.assertEqual(manifest["projects"][0]["purpose"][int(start):int(end)], project_edge["attributes"]["surface"])

    def test_threshold_and_validation(self):
        self.assertEqual(infer_candidate_relations(self.manifest, threshold=0.9)["review_queue"], [])
        with self.assertRaises(ValueError):
            infer_candidate_relations(self.manifest, threshold=1.1)

    def test_empty_or_missing_purpose_is_ignored(self):
        result = infer_candidate_relations({"projects": [{"id": "x", "purpose": ""}]})
        self.assertEqual(result["summary"]["projects"], 0)
        self.assertEqual(result["edges"], [])


if __name__ == "__main__":
    unittest.main()
