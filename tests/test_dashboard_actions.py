from __future__ import annotations
import json
import threading
import unittest
from http.client import HTTPConnection
from pathlib import Path
from tempfile import TemporaryDirectory

from steadfast.dashboard import DashboardHandler, DashboardServer
from steadfast.policy import init_policy


class DashboardActionTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.repo = Path(self.temp.name)
        init_policy(self.repo)
        (self.repo / ".steadfast" / "goal.md").write_text(
            "# Product goal\n\n## Acceptance criteria\n- [ ] User-visible behavior works\n",
            encoding="utf-8",
        )
        self.server = DashboardServer(("127.0.0.1", 0), DashboardHandler)
        self.server.repo = self.repo
        self.server.action_token = "test-token-that-is-long-enough"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.host, self.port = self.server.server_address

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.temp.cleanup()

    def request(self, method, path, payload=None, headers=None):
        connection = HTTPConnection(self.host, self.port, timeout=5)
        body = None if payload is None else json.dumps(payload)
        merged = dict(headers or {})
        if body is not None:
            merged.setdefault("Content-Type", "application/json")
            merged.setdefault("Content-Length", str(len(body.encode("utf-8"))))
        connection.request(method, path, body=body, headers=merged)
        response = connection.getresponse()
        result = response.status, response.read()
        connection.close()
        return result

    def test_console_injects_per_server_action_token(self):
        status, body = self.request("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn(b"test-token-that-is-long-enough", body)
        self.assertNotIn(b"__STEADFAST_ACTION_TOKEN__", body)

    def test_post_without_token_is_rejected(self):
        status, body = self.request("POST", "/api/cycle/start", {"goal_id": "goal"})
        self.assertEqual(status, 403)
        self.assertIn(b"token", body.lower())

    def test_cross_origin_post_is_rejected(self):
        status, _ = self.request("POST", "/api/cycle/start", {"goal_id": "goal"}, {
            "X-Steadfast-Token": self.server.action_token,
            "Origin": "http://attacker.example",
            "Host": f"{self.host}:{self.port}",
        })
        self.assertEqual(status, 403)

    def test_valid_local_action_starts_goal(self):
        status, body = self.request("POST", "/api/cycle/start", {"goal_id": "goal"}, {
            "X-Steadfast-Token": self.server.action_token,
            "Origin": f"http://{self.host}:{self.port}",
            "Host": f"{self.host}:{self.port}",
        })
        self.assertEqual(status, 200, body.decode("utf-8"))
        result = json.loads(body)
        self.assertTrue(result["ok"])
        self.assertEqual(result["result"]["status"], "in_progress")

    def test_automation_catalog_is_available_in_console(self):
        status, body = self.request("GET", "/api/automations")
        self.assertEqual(status, 200)
        result = json.loads(body)
        self.assertIn("quick-health", [item["id"] for item in result["workflows"]])

    def test_automation_run_requires_local_action_token(self):
        status, body = self.request("POST", "/api/automations/run", {"workflow_id": "quick-health"})
        self.assertEqual(status, 403)
        self.assertIn(b"token", body.lower())

    def test_unknown_action_is_not_found(self):
        status, _ = self.request("POST", "/api/cycle/erase", {}, {
            "X-Steadfast-Token": self.server.action_token,
            "Host": f"{self.host}:{self.port}",
        })
        self.assertEqual(status, 404)


if __name__ == "__main__":
    unittest.main()
