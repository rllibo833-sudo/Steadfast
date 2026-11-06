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
