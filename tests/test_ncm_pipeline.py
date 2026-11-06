import json
import unittest
from pathlib import Path

from steadfast.ncm_pipeline import infer_candidate_relations


class NcmPipelineTests(unittest.TestCase):
    def setUp(self):
        self.manifest = {
            "universe_id": "universe-test",
            "manifest_version": "1",
            "title": "Test Universe",
            "sources": [{"id": "github", "type": "git_host", "state": "connected", "scope": "Code repositories"}],
            "consumers": [{"id": "ncm", "role": "Model concepts across projects", "implementation_status": "planned"}],
            "projects": [
                {
                    "id": "alpha", "name": "Alpha", "purpose": "Cyber defense knowledge archive",
                    "sources": [{"source_id": "github", "uri": "https://example.test/alpha", "role": "repository", "title": "Cyber defense archive"}],
                },
                {
                    "id": "beta", "name": "Beta", "purpose": "Digital forensics cyber defense knowledge",
                    "sources": [{"source_id": "missing", "uri": "local://missing", "role": "local"}],
                },
            ],
            "relationships": [],
            "inventory_notes": ["Inventory is partial and not live verified."],
        }

    def test_extracts_multiple_manifest_field_types(self):
        result = infer_candidate_relations(self.manifest)
        kinds = {node["kind"] for node in result["nodes"]}
        self.assertTrue({"project", "source_system", "consumer", "candidate_concept", "universe_inventory", "unresolved_source_reference"} <= kinds)
        self.assertGreater(result["summary"]["candidate_concepts"], 0)

    def test_every_edge_has_existing_endpoints_and_string_evidence(self):
        result = infer_candidate_relations(self.manifest)
        ids = {node["id"] for node in result["nodes"]}
        for edge in result["edges"]:
            self.assertIn(edge["from"], ids)
            self.assertIn(edge["to"], ids)
            self.assertIsInstance(edge["evidence"], str)
            self.assertTrue(edge["evidence"])
            self.assertRegex(edge["edge_id"], r"^edge:[a-f0-9]{24}$")

    def test_overlap_candidate_has_reproducible_field_evidence(self):
        result = infer_candidate_relations(self.manifest)
        edge = next(item for item in result["edges"] if item["type"] == "lexical_project_overlap")
        evidence = json.loads(edge["evidence"])
        self.assertTrue(any("purpose" in field for field in evidence["left_fields"]))
        self.assertTrue(evidence["shared_terms"])
        self.assertEqual(edge["epistemic_status"], "candidate")

    def test_source_links_remain_unverified_manifest_assertions(self):
        result = infer_candidate_relations(self.manifest)
        edge = next(item for item in result["edges"] if item["type"] == "uses_source_system")
        self.assertEqual(edge["epistemic_status"], "manifest_asserted_not_independently_verified")

    def test_deterministic_and_read_only(self):
        before = json.dumps(self.manifest, sort_keys=True)
        first = infer_candidate_relations(self.manifest)
        second = infer_candidate_relations(self.manifest)
        self.assertEqual(first, second)
        self.assertEqual(json.dumps(self.manifest, sort_keys=True), before)
        self.assertFalse(first["semantics"]["canonical_manifest_modified"])
        self.assertFalse(first["semantics"]["remote_sources_read"])

    def test_repository_universe_manifest_produces_integral_graph(self):
        manifest_path = Path(__file__).resolve().parents[1] / "ecosystem" / "universe.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        result = infer_candidate_relations(manifest)
        ids = {node["id"] for node in result["nodes"]}
        self.assertEqual(result["summary"]["projects"], len(manifest["projects"]))
        self.assertEqual(result["graph_findings"], [])
        self.assertTrue(all(edge["from"] in ids and edge["to"] in ids for edge in result["edges"]))
        edge_ids = [edge["edge_id"] for edge in result["edges"]]
        self.assertEqual(len(edge_ids), len(set(edge_ids)))

    def test_threshold_validation(self):
        with self.assertRaises(ValueError):
            infer_candidate_relations(self.manifest, threshold=1.2)


if __name__ == "__main__":
    unittest.main()
