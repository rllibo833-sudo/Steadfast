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
        self.assertNotIn("test-secret-value", str(result))

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
            result = infer_semantic_candidates(self.manifest, allow_remote=True, env={"NCM_API_KEY": "test-secret-value", "NCM_MODEL": "test"})
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["summary"]["concepts"], 1)
        self.assertEqual(result["summary"]["relations"], 1)
        self.assertEqual(result["concepts"][0]["epistemic_status"], "candidate")
        self.assertTrue(result["safety"]["evidence_quotes_verified_against_exact_indexed_source_content"])

    def test_existing_openrouter_secret_is_accepted_as_ncm_key(self):
        response = {"concepts": [], "relations": [], "possible_conflicts": []}
        with patch("steadfast.ncm_semantic._call_model", return_value=response) as model_call:
            result = infer_semantic_candidates(
                self.manifest,
                allow_remote=True,
                env={"JBF_OPENROUTER_API_KEY": "existing-openrouter-secret", "NCM_MODEL": "test-model"},
            )
        self.assertEqual(result["status"], "completed")
        model_call.assert_called_once()


    def test_semantic_validation_gets_one_bounded_repair_attempt(self):
        invalid = {
            "concepts": [{
                "name": "Grounded capability",
                "definition": "A reusable capability grounded in source evidence.",
                "evidence": [{"path": "projects[alpha].purpose", "quote": "fabricated quote"}],
            }],
            "relations": [],
            "possible_conflicts": [],
        }
        repaired = {
            "concepts": [{
                "name": "Grounded capability",
                "definition": "A reusable capability grounded in source evidence.",
                "evidence": [{"path": "projects[alpha].purpose", "quote": "shared knowledge archive"}],
            }],
            "relations": [],
            "possible_conflicts": [],
        }
        with patch("steadfast.ncm_semantic._call_model", side_effect=[invalid, repaired]) as model_call:
            result = infer_semantic_candidates(
                self.manifest, allow_remote=True,
                env={"NCM_API_KEY": "test-secret-value", "NCM_MODEL": "test"},
            )
        self.assertEqual(model_call.call_count, 2)
        self.assertEqual(result["summary"]["concepts"], 1)
        self.assertEqual(result["summary"]["initial_rejected_items"], 1)
        self.assertTrue(result["summary"]["repair_attempted"])
        self.assertEqual(result["findings"], [])

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
            result = infer_semantic_candidates(self.manifest, allow_remote=True, env={"NCM_API_KEY": "test-secret-value", "NCM_MODEL": "test"})
        self.assertEqual(result["summary"]["concepts"], 0)
        self.assertEqual(result["findings"][0]["code"], "UNSUPPORTED_CONCEPT_EVIDENCE")

    def test_malformed_evidence_and_relation_shapes_are_rejected_safely(self):
        response = {
            "concepts": [{
                "name": "Bad path", "definition": "Invalid evidence path.",
                "evidence": [{"path": [], "quote": "shared knowledge archive"}],
            }],
            "relations": [{"from": [], "to": "beta", "type": "supports", "rationale": "bad", "confidence": 0.5, "evidence": []}],
            "possible_conflicts": [],
        }
        with patch("steadfast.ncm_semantic._call_model", return_value=response):
            result = infer_semantic_candidates(self.manifest, allow_remote=True, env={"NCM_API_KEY": "test-secret-value", "NCM_MODEL": "test"})
        self.assertEqual(result["summary"]["concepts"], 0)
        self.assertEqual(result["findings"][0]["code"], "UNSUPPORTED_CONCEPT_EVIDENCE")
        self.assertEqual(result["findings"][1]["code"], "INVALID_RELATION_ENDPOINT")

    def test_document_content_requires_separate_remote_approval_and_can_ground_evidence(self):
        documents = [{
            "document_id": "notion:page-1",
            "content": "This project maintains a shared digital evidence archive.",
            "content_sha256": "abc",
            "status": "read",
        }]
        blocked = infer_semantic_candidates(
            self.manifest, allow_remote=True, source_documents=documents,
            env={"NCM_API_KEY": "test-secret-value", "NCM_MODEL": "test"},
        )
        self.assertEqual(blocked["status"], "blocked")
        self.assertFalse(blocked["safety"]["remote_request_made"])
        response = {
            "concepts": [{
                "name": "Digital evidence archive",
                "definition": "A repository for digital evidence.",
                "evidence": [{
                    "path": "documents[notion:page-1].content",
                    "quote": "shared digital evidence archive",
                }],
            }],
            "relations": [],
            "possible_conflicts": [],
        }
        with patch("steadfast.ncm_semantic._call_model", return_value=response) as model_call:
            result = infer_semantic_candidates(
                self.manifest, allow_remote=True, source_documents=documents,
                allow_source_content_remote=True,
                env={"NCM_API_KEY": "test-secret-value", "NCM_MODEL": "test"},
            )
        self.assertEqual(result["summary"]["concepts"], 1)
        self.assertEqual(result["source_documents_count"], 1)
        self.assertIn("shared digital evidence archive", str(model_call.call_args))

    def test_ecosystem_context_fields_can_ground_semantic_evidence(self):
        from steadfast.ncm_semantic import _validate_candidates

        response = {
            "concepts": [{
                "name": "Governance boundary",
                "definition": "A boundary between validation and modeling.",
                "evidence": [{"path": "consumers[0].role", "quote": "Model concepts across indexed projects"}],
            }],
            "relations": [],
            "possible_conflicts": [],
        }
        concepts, _, _, findings = _validate_candidates(response, {
            **self.manifest,
            "consumers": [{"id": "ncm", "role": "Model concepts across indexed projects"}],
        })
        self.assertEqual(len(concepts), 1)
        self.assertEqual(findings, [])


    def test_adapter_capability_evidence_can_ground_emergent_concepts(self):
        from steadfast.ncm_semantic import _validate_candidates

        adapters = [{
            "project_id": "alpha",
            "adapter_id": "alpha-adapter",
            "status": "completed",
            "capabilities": [{"id": "compiler:frontend", "verification": "smoke_test"}],
            "outputs": [{"kind": "command_result", "exit_code": 0}],
        }]
        response = {
            "concepts": [{
                "name": "Verified compiler frontend",
                "definition": "A compiler frontend whose import path passed its adapter smoke test.",
                "evidence": [{
                    "path": "adapter_results[alpha].capabilities[0].verification",
                    "quote": "smoke_test",
                }],
            }],
            "relations": [],
            "possible_conflicts": [],
        }
        concepts, _, _, findings = _validate_candidates(response, self.manifest, adapter_results=adapters)
        self.assertEqual(len(concepts), 1)
        self.assertEqual(findings, [])

    def test_non_tls_remote_endpoint_is_rejected_before_sending_credentials(self):
        from steadfast.ncm_semantic import _call_model

        with patch("steadfast.ncm_semantic.urllib.request.urlopen") as send:
            with self.assertRaisesRegex(RuntimeError, "must use HTTPS"):
                _call_model(
                    self.manifest,
                    {"NCM_API_KEY": "secret", "NCM_MODEL": "test", "NCM_BASE_URL": "http://example.com/v1"},
                )
        send.assert_not_called()

    def test_local_http_endpoint_is_allowed_for_development(self):
        import json
        from steadfast.ncm_semantic import _call_model

        response = {"choices": [{"message": {"content": '{"concepts":[],"relations":[],"possible_conflicts":[]}'}}]}
        with patch("steadfast.ncm_semantic.urllib.request.urlopen") as send:
            send.return_value.__enter__.return_value.read.return_value = json.dumps(response).encode()
            result = _call_model(
                self.manifest,
                {"NCM_API_KEY": "secret", "NCM_MODEL": "test", "NCM_BASE_URL": "http://localhost:1234/v1"},
            )
        self.assertEqual(result["concepts"], [])
        send.assert_called_once()

    def test_model_json_parser_recovers_fenced_and_prose_wrapped_objects(self):
        import json
        from steadfast.ncm_semantic import _parse_model_json
        expected = {"concepts": [], "relations": [], "possible_conflicts": []}
        self.assertEqual(_parse_model_json("```json\n" + json.dumps(expected) + "\n```"), expected)
        self.assertEqual(_parse_model_json("Result:\n" + json.dumps(expected)), expected)

    def test_semantic_failure_reports_effective_free_model_provider(self):
        from unittest.mock import patch
        from steadfast.ncm_semantic import infer_semantic_candidates

        with patch("steadfast.ncm_semantic._call_model", side_effect=RuntimeError("provider unavailable")):
            result = infer_semantic_candidates(
                self.manifest,
                allow_remote=True,
                env={
                    "NCM_API_KEY": "test-key",
                    "NCM_BASE_URL": "https://openrouter.ai/api/v1",
                    "NCM_MODEL": "openai/gpt-4o-mini",
                },
            )
        self.assertEqual(result["provider"]["model"], "openrouter/free")
        self.assertEqual(result["provider"]["configured_model"], "openai/gpt-4o-mini")
        self.assertTrue(result["provider"]["free_only"])

    def test_openrouter_provider_metadata_reports_effective_free_model(self):
        from steadfast.ncm_semantic import _provider_metadata
        provider = _provider_metadata({
            "NCM_BASE_URL": "https://openrouter.ai/api/v1",
            "NCM_MODEL": "openai/gpt-4o-mini",
        })
        self.assertEqual(provider["model"], "openrouter/free")
        self.assertEqual(provider["configured_model"], "openai/gpt-4o-mini")
        self.assertTrue(provider["free_only"])
    def test_openrouter_is_forced_to_free_router_model(self):
        import json
        from unittest.mock import patch
        from steadfast.ncm_semantic import _call_model

        response_body = {"choices": [{"message": {"content": '{"concepts":[],"relations":[],"possible_conflicts":[]}'}}]}
        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def read(self, limit): return json.dumps(response_body).encode()

        with patch("steadfast.ncm_semantic.urllib.request.urlopen", return_value=Response()) as request:
            _call_model(
                self.manifest,
                {
                    "NCM_API_KEY": "test-key",
                    "NCM_BASE_URL": "https://openrouter.ai/api/v1",
                    "NCM_MODEL": "openai/gpt-4o-mini",
                },
            )
        sent = json.loads(request.call_args.args[0].data.decode())
        self.assertEqual(sent["model"], "openrouter/free")

    def test_http_provider_failure_reports_status_without_response_body(self):
        import urllib.error
        from unittest.mock import patch
        from steadfast.ncm_semantic import _call_model

        error = urllib.error.HTTPError(
            "https://provider.example/v1/chat/completions", 403, "Forbidden",
            {}, None,
        )
        with patch("steadfast.ncm_semantic.urllib.request.urlopen", side_effect=error):
            with self.assertRaisesRegex(RuntimeError, "HTTP 403"):
                _call_model(
                    self.manifest,
                    {"NCM_API_KEY": "secret", "NCM_MODEL": "test"},
                )

    def test_incomplete_model_response_schema_is_rejected(self):
        import json
        from steadfast.ncm_semantic import _call_model

        response = {"choices": [{"message": {"content": '{"concepts":[]}'}}]}
        with patch("steadfast.ncm_semantic.urllib.request.urlopen") as send:
            send.return_value.__enter__.return_value.read.return_value = json.dumps(response).encode()
            with self.assertRaisesRegex(RuntimeError, "must contain concepts"):
                _call_model(self.manifest, {"NCM_API_KEY": "secret", "NCM_MODEL": "test"})


if __name__ == "__main__":
    unittest.main()
