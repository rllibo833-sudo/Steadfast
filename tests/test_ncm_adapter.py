from __future__ import annotations

import unittest

from steadfast.ncm_adapter import build_concept_model


class NCMAdapterTests(unittest.TestCase):
    def test_builds_provenance_preserving_graph(self):
        manifest = {
            "universe_id": "test-universe",
            "manifest_version": "1.0",
            "sources": [{"id": "github", "type": "git_host", "state": "connected"}],
            "projects": [{
                "id": "alpha",
                "name": "Alpha",
                "purpose": "A sample compiler project.",
                "status": "unverified",
                "sources": [{
                    "source_id": "github",
                    "uri": "https://github.com/example/alpha",
                    "role": "repository",
                }],
            }],
            "relationships": [{
                "from": "alpha",
                "to": "ncm",
                "type": "feeds_model",
                "status": "proposed",
            }],
        }
        audit = {
            "check": "universe-manifest",
            "findings": [{
                "code": "EXAMPLE_WARNING",
                "severity": "warning",
                "path": "projects[0]",
                "message": "Example only",
            }],
        }

        model = build_concept_model(manifest, audit)
        kinds = [node["kind"] for node in model["nodes"]]
        self.assertIn("project", kinds)
        self.assertIn("source_system", kinds)
        self.assertIn("declared_concept", kinds)
        self.assertIn("audit_finding", kinds)
        self.assertFalse(model["semantics"]["inference_performed"])
        self.assertFalse(model["semantics"]["relationships_are_verified"])
        self.assertTrue(any(edge["type"] == "uses_source_system" for edge in model["edges"]))
        self.assertTrue(any(edge["type"] == "feeds_model" for edge in model["edges"]))

    def test_duplicate_sources_do_not_duplicate_source_nodes(self):
        manifest = {
            "sources": [{"id": "github"}, {"id": "github"}],
            "projects": [],
            "relationships": [],
        }
        model = build_concept_model(manifest)
        source_nodes = [node for node in model["nodes"] if node["kind"] == "source_system"]
        self.assertEqual(len(source_nodes), 1)


if __name__ == "__main__":
    unittest.main()
