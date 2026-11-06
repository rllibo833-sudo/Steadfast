import io
import socket
import unittest
import urllib.error
from unittest.mock import patch

from steadfast.ncm_backends import probe_backend_services


class BackendProbeTests(unittest.TestCase):
    def test_records_ready_and_auth_protected_services_without_credentials(self):
        class Response:
            def __init__(self, status, body, content_type="application/json"):
                self.status = status
                self.headers = {"Content-Type": content_type}
                self.body = body

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self, limit):
                return self.body[:limit]

        manifest = {"backend_services": [
            {"id": "public", "project_id": "alpha", "endpoint": "https://alpha.supabase.co/functions/v1/health", "auth_mode": "public", "expected_status": [200]},
            {"id": "private", "project_id": "beta", "endpoint": "https://beta.supabase.co/functions/v1/mcp", "auth_mode": "required", "expected_status": [401, 403]},
        ]}
        with patch("steadfast.ncm_backends.urllib.request.urlopen", side_effect=[
            Response(200, b'{"status":"ok"}'),
            urllib.error.HTTPError(
                "https://beta.supabase.co/functions/v1/mcp", 401, "Unauthorized", {}, io.BytesIO(b"auth required")
            ),
        ]):
            result = probe_backend_services(manifest)

        self.assertEqual(result["summary"], {
            "services": 2, "ready": 1, "reachable_auth_required": 1, "failed": 0,
        })
        self.assertEqual(result["results"][0]["status"], "ready")
        self.assertEqual(result["results"][1]["status"], "reachable_auth_required")
        self.assertFalse(result["safety"]["credentials_sent"])
        self.assertFalse(result["safety"]["database_writes"])

    def test_rejects_non_supabase_endpoint(self):
        result = probe_backend_services({"backend_services": [{
            "id": "bad", "project_id": "alpha", "endpoint": "https://example.com/functions/v1/health",
        }]})
        self.assertEqual(result["summary"]["failed"], 1)
        self.assertEqual(result["results"][0]["findings"][0]["code"], "BACKEND_PROBE_ENDPOINT_NOT_ALLOWLISTED")

    def test_exposes_underlying_dns_failure_for_diagnostics(self):
        manifest = {"backend_services": [{
            "id": "dns", "project_id": "alpha",
            "endpoint": "https://alpha.supabase.co/functions/v1/health",
            "auth_mode": "public", "expected_status": [200],
        }]}
        error = urllib.error.URLError(socket.gaierror(-2, "Name or service not known"))
        with patch("steadfast.ncm_backends.urllib.request.urlopen", side_effect=error):
            result = probe_backend_services(manifest)

        finding = result["results"][0]["findings"][0]
        self.assertEqual(finding["code"], "BACKEND_DNS_RESOLUTION_FAILED")
        self.assertEqual(finding["error_type"], "gaierror")
        self.assertIn("Name or service not known", finding["error_reason"])


if __name__ == "__main__":
    unittest.main()
