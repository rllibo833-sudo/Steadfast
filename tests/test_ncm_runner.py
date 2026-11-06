import unittest
from unittest.mock import patch

from steadfast.ncm_adapters import AdapterRegistry, AdapterResult
from steadfast.ncm_runner import render_ncm, run_ncm


class NcmRunnerTests(unittest.TestCase):
    def setUp(self):
        self.manifest = {
            "universe_id": "test",
            "projects": [{"id": "alpha"}, {"id": "beta"}],
        }
        self.ingestion = {
            "documents": [{
                "document_id": "notion:alpha",
                "project_id": "alpha",
                "source_id": "notion",
                "content": "shared evidence archive",
                "status": "read",
            }],
            "summary": {"documents_read": 1},
            "failures": [],
            "safety": {"read_only": True},
        }
        self.graph = {
            "nodes": [
                {"id": "project:alpha", "kind": "project", "label": "Alpha"},
                {"id": "project:beta", "kind": "project", "label": "Beta"},
            ],
            "edges": [],
            "summary": {
                "projects": 2,
                "candidate_concepts": 3,
                "cross_project_relations": 1,
            },
            "documents": [{"document_id": "notion:alpha"}],
            "graph_findings": [],
            "manifest_findings": [],
        }

    @patch("steadfast.ncm_runner.infer_semantic_candidates")
    @patch("steadfast.ncm_runner.build_cross_project_model")
    @patch("steadfast.ncm_runner.collect_source_documents")
    @patch("steadfast.ncm_runner.load_universe_manifest")
    def test_one_runner_executes_and_combines_all_ncm_layers(
        self, load_manifest, collect, build_graph, semantic
    ):
        load_manifest.return_value = (self.manifest, [])
        collect.return_value = self.ingestion
        build_graph.return_value = self.graph
        semantic.return_value = {
            "status": "completed",
            "concepts": [{"id": "candidate-concept:1"}],
            "relations": [{"from": "project:alpha", "to": "project:beta", "type": "supports", "rationale": "shared workflow", "confidence": 0.8, "evidence": [{"path": "projects[alpha].purpose", "quote": "archive"}]}],
            "possible_conflicts": [],
            "findings": [],
            "summary": {"concepts": 1, "relations": 1},
            "safety": {"remote_request_made": True},
        }

        result = run_ncm("/tmp/repo", allow_remote=True)

        load_manifest.assert_called_once()
        collect.assert_called_once_with(self.manifest, env=None)
        build_graph.assert_called_once_with(self.manifest, self.ingestion["documents"], threshold=0.2)
        semantic.assert_called_once_with(
            self.manifest,
            allow_remote=True,
            env=None,
            source_documents=[],
            allow_source_content_remote=False,
            adapter_results=[
                {"project_id": "alpha", "adapter_id": None, "status": "not_configured", "capabilities": [], "outputs": [], "dependencies": [], "findings": [{"code": "ADAPTER_NOT_DECLARED"}]},
                {"project_id": "beta", "adapter_id": None, "status": "not_configured", "capabilities": [], "outputs": [], "dependencies": [], "findings": [{"code": "ADAPTER_NOT_DECLARED"}]},
            ],
        )
        self.assertEqual(result["model_type"], "next_concept_model")
        self.assertEqual(len(result["ecosystem_graph"]["nodes"]), 3)
        self.assertEqual(len(result["ecosystem_graph"]["edges"]), 1)
        self.assertEqual(result["ecosystem_graph"]["edges"][0]["epistemic_status"], "candidate")
        self.assertEqual(result["semantic_layer"]["status"], "completed")
        self.assertEqual(result["summary"]["candidate_concepts"], 4)
        self.assertEqual(result["summary"]["cross_project_relations"], 2)
        self.assertEqual(result["summary"]["source_failures"], 0)
        self.assertEqual(result["summary"]["semantic_rejected_items"], 0)

    @patch("steadfast.ncm_runner.infer_semantic_candidates")
    @patch("steadfast.ncm_runner.build_cross_project_model")
    @patch("steadfast.ncm_runner.collect_source_documents")
    @patch("steadfast.ncm_runner.load_universe_manifest")
    def test_source_text_is_not_sent_without_separate_consent(
        self, load_manifest, collect, build_graph, semantic
    ):
        load_manifest.return_value = (self.manifest, [])
        collect.return_value = self.ingestion
        build_graph.return_value = self.graph
        semantic.return_value = {"status": "blocked", "safety": {"remote_request_made": False}}

        result = run_ncm("/tmp/repo", allow_remote=True)

        self.assertEqual(semantic.call_args.kwargs["source_documents"], [])
        self.assertFalse(result["safety"]["source_documents_sent_to_model"])

    @patch("steadfast.ncm_runner.load_universe_manifest")
    def test_invalid_manifest_stops_pipeline(self, load_manifest):
        load_manifest.return_value = (None, [{"code": "INVALID"}])
        result = run_ncm("/tmp/repo")
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["manifest_findings"], [{"code": "INVALID"}])


    def test_adapter_capabilities_are_merged_into_the_ecosystem_graph(self):
        manifest = {
            "universe_id": "test",
            "projects": [{"id": "alpha", "adapter": {"id": "alpha-adapter"}}],
        }
        graph = {
            "nodes": [{"id": "project:alpha", "kind": "project", "label": "Alpha"}],
            "edges": [],
            "summary": {"projects": 1, "candidate_concepts": 0, "cross_project_relations": 0},
            "documents": [],
            "graph_findings": [],
            "manifest_findings": [],
        }

        class AlphaAdapter:
            adapter_id = "alpha-adapter"

            def __call__(self, context):
                return AdapterResult(
                    project_id="alpha",
                    adapter_id=self.adapter_id,
                    status="completed",
                    capabilities=[{"id": "alpha:capability", "name": "Verified capability"}],
                    outputs=[{"kind": "smoke_test", "exit_code": 0}],
                )

        registry = AdapterRegistry()
        registry.register(AlphaAdapter())
        with patch("steadfast.ncm_runner.load_universe_manifest", return_value=(manifest, [])), \
             patch("steadfast.ncm_runner.collect_source_documents", return_value={"documents": [], "failures": [], "summary": {}, "safety": {}}), \
             patch("steadfast.ncm_runner.build_cross_project_model", return_value=graph), \
             patch("steadfast.ncm_runner.infer_semantic_candidates", return_value={"status": "completed", "concepts": [], "relations": [], "possible_conflicts": [], "findings": [], "summary": {}, "safety": {}}):
            result = run_ncm("/tmp/repo", adapter_registry=registry)

        nodes = result["ecosystem_graph"]["nodes"]
        edges = result["ecosystem_graph"]["edges"]
        self.assertTrue(any(node["kind"] == "verified_project_capability" for node in nodes))
        self.assertTrue(any(edge["type"] == "exposes_verified_capability" for edge in edges))
        self.assertEqual(result["summary"]["adapter_capabilities"], 1)
        self.assertEqual(result["summary"]["adapter_outputs"], 1)


    def test_emergent_synthesis_is_merged_into_the_single_ecosystem_graph(self):
        projects = ["pusingcuk", "mnemos-rli", "steadfast"]
        manifest = {
            "universe_id": "test",
            "projects": [{"id": item, "adapter": {"id": "smoke"}} for item in projects],
        }
        graph = {
            "nodes": [{"id": f"project:{item}", "kind": "project", "label": item} for item in projects],
            "edges": [],
            "summary": {"projects": 3, "candidate_concepts": 0, "cross_project_relations": 0},
            "documents": [],
            "graph_findings": [],
            "manifest_findings": [],
        }

        class SmokeAdapter:
            adapter_id = "smoke"

            def __call__(self, context):
                return AdapterResult(
                    project_id=context.project["id"],
                    adapter_id=self.adapter_id,
                    status="completed",
                    capabilities=[{"id": f"{context.project['id']}:smoke", "verification": "smoke_test"}],
                )

        registry = AdapterRegistry()
        registry.register(SmokeAdapter())
        with patch("steadfast.ncm_runner.load_universe_manifest", return_value=(manifest, [])), \
             patch("steadfast.ncm_runner.collect_source_documents", return_value={"documents": [], "failures": [], "summary": {}, "safety": {}}), \
             patch("steadfast.ncm_runner.build_cross_project_model", return_value=graph), \
             patch("steadfast.ncm_runner.infer_semantic_candidates", return_value={"status": "blocked", "concepts": [], "relations": [], "possible_conflicts": [], "findings": [], "summary": {}, "safety": {}}):
            result = run_ncm("/tmp/repo", adapter_registry=registry)

        self.assertEqual(result["summary"]["emergent_concepts"], 1)
        self.assertEqual(result["summary"]["orchestration_relations"], 2)
        self.assertTrue(any(node["kind"] == "emergent_ecosystem_concept" for node in result["ecosystem_graph"]["nodes"]))
        self.assertEqual(sum(edge["type"] == "verified_by_shared_ncm_orchestrator" for edge in result["ecosystem_graph"]["edges"]), 2)
        self.assertEqual(result["ecosystem_graph"]["summary"]["nodes"], len(result["ecosystem_graph"]["nodes"]))

    def test_verified_cross_project_contract_becomes_two_graph_edges(self):
        manifest = {
            "universe_id": "test",
            "projects": [{"id": "alpha", "adapter": {"id": "bridge"}}, {"id": "beta"}],
        }
        graph = {
            "nodes": [
                {"id": "project:alpha", "kind": "project", "label": "Alpha"},
                {"id": "project:beta", "kind": "project", "label": "Beta"},
            ],
            "edges": [],
            "summary": {"projects": 2, "candidate_concepts": 0, "cross_project_relations": 0},
            "documents": [], "graph_findings": [], "manifest_findings": [],
        }

        class BridgeAdapter:
            adapter_id = "bridge"

            def __call__(self, context):
                return AdapterResult(
                    project_id="alpha", adapter_id="bridge", status="completed",
                    outputs=[{
                        "kind": "cross_project_integration",
                        "contract": "alpha-beta-v1",
                        "producer_project": "alpha",
                        "consumer_project": "beta",
                    }],
                )

        registry = AdapterRegistry()
        registry.register(BridgeAdapter())
        with patch("steadfast.ncm_runner.load_universe_manifest", return_value=(manifest, [])), \\
             patch("steadfast.ncm_runner.collect_source_documents", return_value={"documents": [], "failures": [], "summary": {}, "safety": {}}), \\
             patch("steadfast.ncm_runner.build_cross_project_model", return_value=graph), \\
             patch("steadfast.ncm_runner.infer_semantic_candidates", return_value={"status": "blocked", "concepts": [], "relations": [], "possible_conflicts": [], "findings": [], "summary": {}, "safety": {}}):
            result = run_ncm("/tmp/repo", adapter_registry=registry)

        edge_types = {edge["type"] for edge in result["ecosystem_graph"]["edges"]}
        self.assertIn("provided_cross_project_payload", edge_types)
        self.assertIn("consumed_cross_project_payload", edge_types)

    def test_rendered_artifact_is_single_json_document_with_newline(self):
        rendered = render_ncm({"model_type": "next_concept_model"})
        self.assertTrue(rendered.endswith("\n"))
        self.assertTrue(rendered.startswith("{"))


if __name__ == "__main__":
    unittest.main()
