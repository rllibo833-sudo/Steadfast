import copy
import hashlib
import unittest

from steadfast.ncm_cross_project import build_cross_project_model


class NcmCrossProjectTests(unittest.TestCase):
    def setUp(self):
        self.manifest = {
            "universe_id": "test-universe",
            "manifest_version": "1.0.0",
            "sources": [
                {"id": "github", "type": "git_host", "state": "connected"},
                {"id": "notion", "type": "knowledge_workspace", "state": "connected"},
            ],
            "consumers": [{"id": "ncm", "role": "Model concepts across indexed projects", "implementation_status": "planned"}],
            "projects": [
                {"id": "alpha", "name": "Alpha", "purpose": "Digital forensics knowledge archive", "status": "documented",
                 "sources": [{"source_id": "github", "uri": "https://example.test/alpha", "role": "repository"}]},
                {"id": "beta", "name": "Beta", "purpose": "Cyber defense research archive", "status": "unverified",
                 "sources": [{"source_id": "github", "uri": "https://example.test/beta", "role": "repository"}]},
                {"id": "gamma", "name": "Gamma", "purpose": "Solar system simulation", "status": "unverified",
                 "sources": [{"source_id": "notion", "uri": "https://example.test/gamma", "role": "documentation"}]},
            ],
            "relationships": [
                {"from": "alpha", "to": "ncm", "type": "consumer_input", "status": "proposed"}
            ],
            "inventory_notes": ["Partial inventory; source states are not independently verified."],
        }
        self.documents = [
            {
                "document_id": "notion:alpha",
                "project_id": "alpha",
                "source_id": "notion",
                "title": "Alpha knowledge notes",
                "uri": "https://example.test/alpha-notes",
                "content": "Digital forensics and cyber defense knowledge archive.",
                "status": "read",
            },
            {
                "document_id": "github:beta",
                "project_id": "beta",
                "source_id": "github",
                "title": "Beta README",
                "uri": "https://example.test/beta",
                "content": "Cyber defense knowledge archive for digital forensics.",
                "status": "partial",
            },
        ]
        for document in self.documents:
            document["content_sha256"] = hashlib.sha256(document["content"].encode()).hexdigest()

    def test_builds_cross_project_concepts_and_evidence_relations(self):
        result = build_cross_project_model(self.manifest, self.documents)
        self.assertEqual(result["model_type"], "ncm_cross_project_concept_graph")
        self.assertEqual(result["summary"]["documents"], 2)
        self.assertGreater(result["summary"]["shared_concepts_across_projects"], 0)
        self.assertGreater(result["summary"]["cross_project_relations"], 0)
        relation = next(edge for edge in result["edges"] if edge["type"] == "cross_project_shared_evidence")
        self.assertEqual(relation["epistemic_status"], "candidate")
        self.assertIn("cyber", relation["attributes"]["shared_concepts"])
        ids = {node["id"] for node in result["nodes"]}
        self.assertTrue(all(edge["from"] in ids and edge["to"] in ids for edge in result["edges"]))
        self.assertEqual(result["graph_findings"], [])

    def test_documents_are_referenced_but_content_is_not_embedded(self):
        result = build_cross_project_model(self.manifest, self.documents)
        rendered = str(result)
        self.assertNotIn("Digital forensics and cyber defense knowledge archive.", rendered)
        self.assertTrue(result["semantics"]["source_document_text_embedded"] is False)
        self.assertTrue(all("content" not in item for item in result["documents"]))

    def test_digest_mismatch_is_rejected(self):
        bad = copy.deepcopy(self.documents)
        bad[0]["content_sha256"] = "0" * 64
        result = build_cross_project_model(self.manifest, bad)
        self.assertEqual(result["summary"]["documents"], 1)
        self.assertEqual(result["source_document_findings"][0]["code"], "DOCUMENT_DIGEST_MISMATCH")

    def test_unresolved_project_and_unreadable_documents_are_findings(self):
        docs = [
            {"document_id": "orphan", "project_id": "missing", "content": "some words", "status": "read"},
            {"document_id": "blocked", "project_id": "alpha", "content": "private text", "status": "unavailable"},
        ]
        result = build_cross_project_model(self.manifest, docs)
        codes = {item["code"] for item in result["source_document_findings"]}
        self.assertEqual(codes, {"UNRESOLVED_DOCUMENT_PROJECT", "DOCUMENT_NOT_USABLE"})
        self.assertEqual(result["summary"]["documents"], 0)

    def test_deterministic_and_manifest_is_read_only(self):
        before = copy.deepcopy(self.manifest)
        first = build_cross_project_model(self.manifest, self.documents)
        second = build_cross_project_model(self.manifest, self.documents)
        self.assertEqual(first, second)
        self.assertEqual(self.manifest, before)
        self.assertFalse(first["semantics"]["canonical_manifest_modified"])

    def test_duplicate_document_ids_are_reported(self):
        docs = copy.deepcopy(self.documents)
        docs.append(copy.deepcopy(docs[0]))
        result = build_cross_project_model(self.manifest, docs)
        self.assertIn("DUPLICATE_DOCUMENT_ID", {item["code"] for item in result["source_document_findings"]})

    def test_threshold_validation(self):
        with self.assertRaises(ValueError):
            build_cross_project_model(self.manifest, threshold=1.1)


if __name__ == "__main__":
    unittest.main()
