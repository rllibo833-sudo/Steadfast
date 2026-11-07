import unittest

from steadfast.ncm_adapters import AdapterContext, AdapterRegistry, AdapterResult, run_project_adapters, DocumentedOnlyAdapter, CrossProjectIntegrationAdapter, derive_ecosystem_synthesis


class ExampleAdapter:
    adapter_id = "example"

    def __call__(self, context: AdapterContext) -> AdapterResult:
        return AdapterResult(
            project_id=context.project["id"],
            adapter_id=self.adapter_id,
            status="completed",
            capabilities=[{"id": "capability:example", "name": "Example capability"}],
        )


class NcmAdapterTests(unittest.TestCase):
    def test_unconfigured_projects_are_reported_without_execution(self):
        result = run_project_adapters({"projects": [{"id": "alpha"}]}, [])
        self.assertEqual(result["summary"]["not_configured"], 1)
        self.assertEqual(result["results"][0]["findings"][0]["code"], "ADAPTER_NOT_DECLARED")

    def test_declared_but_unregistered_adapter_fails_closed(self):
        result = run_project_adapters(
            {"projects": [{"id": "alpha", "adapter": {"id": "missing"}}]}, []
        )
        self.assertEqual(result["summary"]["unavailable"], 1)
        self.assertEqual(result["results"][0]["findings"][0]["code"], "ADAPTER_NOT_REGISTERED")

    def test_registered_adapter_receives_only_its_project_documents(self):
        registry = AdapterRegistry()
        registry.register(ExampleAdapter())
        result = run_project_adapters(
            {"projects": [{"id": "alpha", "adapter": {"id": "example"}}]},
            [
                {"project_id": "alpha", "content": "alpha source"},
                {"project_id": "beta", "content": "beta source"},
            ],
            registry,
        )
        self.assertEqual(result["summary"]["executed"], 1)
        self.assertEqual(result["results"][0]["status"], "completed")
        self.assertEqual(result["results"][0]["capabilities"][0]["id"], "capability:example")


    def test_documented_only_projects_are_explicitly_not_executable(self):
        registry = AdapterRegistry()
        registry.register(DocumentedOnlyAdapter())
        result = run_project_adapters(
            {"projects": [{"id": "archive", "adapter": {"id": "documented-only"}}]},
            [],
            registry,
        )
        self.assertEqual(result["results"][0]["status"], "documented_only")
        self.assertEqual(result["summary"]["documented_only"], 1)
        self.assertEqual(result["status"], "completed")


    def test_synthesis_derives_shared_verification_from_three_completed_projects(self):
        result = derive_ecosystem_synthesis({
            "results": [
                {"project_id": "pusingcuk", "status": "completed"},
                {"project_id": "mnemos-rli", "status": "completed"},
                {"project_id": "steadfast", "status": "completed"},
                {"project_id": "ecos", "status": "archived"},
            ]
        })
        self.assertEqual(result["summary"]["emergent_concepts"], 1)
        self.assertEqual(result["summary"]["orchestration_relations"], 2)
        self.assertEqual(result["emergent_concepts"][0]["epistemic_status"], "candidate")
        self.assertEqual(result["safety"]["inferred_dependencies"], False)

    def test_synthesis_does_not_infer_integration_from_two_non_orchestrator_projects(self):
        result = derive_ecosystem_synthesis({
            "results": [
                {"project_id": "pusingcuk", "status": "completed"},
                {"project_id": "mnemos-rli", "status": "completed"},
            ]
        })
        self.assertEqual(result["summary"]["emergent_concepts"], 0)
        self.assertEqual(result["summary"]["orchestration_relations"], 0)

    def test_cross_project_adapter_fails_closed_without_both_source_roots(self):
        adapter = CrossProjectIntegrationAdapter()
        context = AdapterContext(
            project={"id": "steadfast"},
            source_documents=(),
            ecosystem_manifest={"projects": []},
            project_roots={},
        )
        result = adapter(context)
        self.assertEqual(result.status, "unavailable")
        self.assertEqual(result.findings[0]["code"], "CROSS_PROJECT_SOURCE_MISSING")

    def test_cross_project_bridge_reports_mnemos_graph_composition(self):
        import json
        import subprocess
        import tempfile
        from pathlib import Path
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as directory:
            pusingcuk = Path(directory) / "pusingcuk"
            mnemos = Path(directory) / "mnemos"
            pusingcuk.mkdir()
            mnemos.mkdir()
            context = AdapterContext(
                project={"id": "steadfast"},
                source_documents=(),
                ecosystem_manifest={"projects": []},
                project_roots={"pusingcuk": pusingcuk, "mnemos-rli": mnemos},
            )
            output = {
                "contract": "pusingcuk-ir-v1",
                "producer_project": "pusingcuk",
                "consumer_project": "mnemos-rli",
                "validated": True,
                "persisted": True,
                "idempotent": True,
                "compiler_features": ["core", "variables"],
                "mnemos_memory_graph": {
                    "nodes": 3,
                    "relationships": 2,
                    "kinds": {"pusingcuk_compiler_ir": 1, "pusingcuk_ir_feature": 2},
                },
            }
            completed = subprocess.CompletedProcess(
                args=["python", "-c", "..."], returncode=0,
                stdout=json.dumps(output), stderr="",
            )
            with patch("steadfast.ncm_adapters.subprocess.run", return_value=completed) as run:
                result = CrossProjectIntegrationAdapter()(context)

        self.assertEqual(result.status, "completed")
        bridge_source = run.call_args.args[0][2]
        self.assertIn("from mnemos.graph import graph_payload", bridge_source)
        self.assertIn("exposes_compiler_feature", bridge_source)
        self.assertEqual(result.outputs[0]["mnemos_memory_graph"]["nodes"], 3)
        self.assertEqual(result.outputs[0]["mnemos_memory_graph"]["relationships"], 2)

    def test_jbf_cloud_agent_adapter_reports_live_connectors_and_providers(self):
        import json
        import os
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        from steadfast.ncm_adapters import JbfCloudAgentAdapter

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "kits" / "jbf-cloud-agent" / "src" / "index.ts"
            source.parent.mkdir(parents=True)
            source.write_text('import { Agent } from "agents"; export class JbfAgent extends Agent {} addMcpServer awaiting_owner_approval ctx.storage.put openrouter/free', encoding="utf-8")
            context = AdapterContext(
                project={"id": "jbf-cloud-agent"}, source_documents=(),
                ecosystem_manifest={"projects": []}, project_roots={"steadfast": root},
            )
            status_payload = {
                "connectors": [{"id": "github", "connected": True}],
                "tools": [{"serverId": "github", "name": "search_repositories", "readOnly": True}],
                "approvals": [{"status": "pending"}],
            }
            provider_payload = {"providers": [{"id": "github", "connected": True, "state": "ready"}]}
            class Response:
                status = 200
                def __init__(self, payload): self.payload = payload
                def __enter__(self): return self
                def __exit__(self, *args): return False
                def read(self, limit): return json.dumps(self.payload).encode()
            with patch.dict(os.environ, {"JBF_OWNER_TOKEN": "test-token"}), patch(
                "urllib.request.urlopen", side_effect=[Response(status_payload), Response(provider_payload)]
            ) as request:
                result = JbfCloudAgentAdapter()(context)

        self.assertEqual(result.status, "completed")
        self.assertEqual(result.outputs[0]["kind"], "jbf_agent_code_inventory")
        self.assertEqual(result.outputs[1]["connected_connectors"], ["github"])
        self.assertEqual(result.outputs[1]["pending_owner_approvals"], 1)
        self.assertEqual(result.outputs[1]["provider_inventory"][0]["id"], "github")
        self.assertTrue(all(call.args[0].method == "GET" for call in request.call_args_list))

    def test_jbf_cloud_agent_adapter_preserves_source_capabilities_when_runtime_is_forbidden(self):
        import os
        import tempfile
        import urllib.error
        from pathlib import Path
        from unittest.mock import patch
        from steadfast.ncm_adapters import JbfCloudAgentAdapter

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "kits" / "jbf-cloud-agent" / "src" / "index.ts"
            source.parent.mkdir(parents=True)
            source.write_text('import { Agent } from "agents";\\nexport class JbfAgent extends Agent {}\\naddMcpServer awaiting_owner_approval ctx.storage.put openrouter/free', encoding="utf-8")
            context = AdapterContext(
                project={"id": "jbf-cloud-agent"}, source_documents=(),
                ecosystem_manifest={"projects": []}, project_roots={"steadfast": root},
            )
            forbidden = urllib.error.HTTPError("https://worker.example/status", 403, "Forbidden", {}, None)
            with patch.dict(os.environ, {"JBF_OWNER_TOKEN": "test-token"}), patch("urllib.request.urlopen", side_effect=forbidden):
                result = JbfCloudAgentAdapter()(context)

        self.assertEqual(result.status, "partial")
        self.assertEqual(result.outputs[0]["kind"], "jbf_agent_code_inventory")
        self.assertEqual(result.findings[0]["code"], "JBF_AGENT_FORBIDDEN")
        self.assertIn("jbf:owner-approval-gate", [item["id"] for item in result.capabilities])

    def test_jbf_cloud_agent_source_inventory_does_not_require_runtime_credentials(self):
        import os
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        from steadfast.ncm_adapters import JbfCloudAgentAdapter

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "kits" / "jbf-cloud-agent" / "src" / "index.ts"
            source.parent.mkdir(parents=True)
            source.write_text('import { Agent } from "agents";\\nexport class JbfAgent extends Agent {}', encoding="utf-8")
            context = AdapterContext(
                project={"id": "jbf-cloud-agent"}, source_documents=(),
                ecosystem_manifest={"projects": []}, project_roots={"steadfast": root},
            )
            with patch.dict(os.environ, {"JBF_OWNER_TOKEN": ""}):
                result = JbfCloudAgentAdapter()(context)

        self.assertEqual(result.status, "partial")
        self.assertEqual(result.findings[0]["code"], "JBF_AGENT_OWNER_TOKEN_NOT_CONFIGURED")
        self.assertIn("jbf:cloud-agent-runtime", [item["id"] for item in result.capabilities])

    def test_manifest_distinguishes_jbf_cloud_agent_from_sandboxos(self):
        import json
        from pathlib import Path

        manifest = json.loads(
            (Path(__file__).resolve().parents[1] / "ecosystem" / "universe.json").read_text(encoding="utf-8")
        )
        projects = {item["id"]: item for item in manifest["projects"]}
        self.assertEqual(projects["jbf-sandboxos"]["adapter"]["id"], "documented-only")
        self.assertEqual(projects["jbf-cloud-agent"]["adapter"]["id"], "jbf-cloud-agent")
        self.assertIn("Cloudflare Agents SDK", projects["jbf-cloud-agent"]["purpose"])

    def test_duplicate_adapter_registration_is_rejected(self):
        registry = AdapterRegistry()
        registry.register(ExampleAdapter())
        with self.assertRaises(ValueError):
            registry.register(ExampleAdapter())

    def test_adapter_exceptions_are_isolated(self):
        class BrokenAdapter:
            adapter_id = "broken"

            def __call__(self, context):
                raise RuntimeError("do not leak exception message")

        registry = AdapterRegistry()
        registry.register(BrokenAdapter())
        result = run_project_adapters(
            {"projects": [{"id": "alpha", "adapter": {"id": "broken"}}]}, [], registry
        )
        self.assertEqual(result["summary"]["failed"], 1)
        self.assertEqual(result["results"][0]["findings"][0]["error_type"], "RuntimeError")
        self.assertNotIn("do not leak", str(result))


if __name__ == "__main__":
    unittest.main()
