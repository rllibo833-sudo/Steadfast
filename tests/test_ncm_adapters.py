import unittest

from steadfast.ncm_adapters import AdapterContext, AdapterRegistry, AdapterResult, run_project_adapters


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
