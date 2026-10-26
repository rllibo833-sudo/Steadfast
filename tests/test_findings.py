from __future__ import annotations
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from steadfast.findings import (
    finding_history, finding_metrics, list_findings, resolve_finding,
    scan_findings, triage_finding,
)

def finding(code="RULE_X", path="src/app.py", severity="error", message="A real finding"):
    return {"code": code, "path": path, "severity": severity, "message": message}

class FindingLedgerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        self.live = [finding()]
        self.summary = {"audit_passed": False, "audit_summary": {"errors": 1},
                        "product_code_lines": 20, "product_code_budget": 20000,
                        "release_ready": False, "release_blockers": ["audit failed"]}
        self.patch = patch("steadfast.findings._collect", side_effect=lambda _repo: (list(self.live), dict(self.summary)))
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.tmp.cleanup()

    def test_scan_deduplicates_and_preserves_triage_metadata(self):
        first = scan_findings(self.repo)
        self.assertEqual(first["opened"], 1)
        fid = first["findings"][0]["id"]
        triage_finding(self.repo, fid, state="triaged", owner="maintainer", priority="critical", due_date="2099-01-01")
        self.live[0]["message"] = "Updated diagnostic text"
        second = scan_findings(self.repo)
        item = next(x for x in second["findings"] if x["id"] == fid)
        self.assertEqual(second["opened"], 0)
        self.assertEqual(item["state"], "triaged")
        self.assertEqual(item["owner"], "maintainer")
        self.assertEqual(item["priority"], "critical")
        self.assertEqual(item["message"], "Updated diagnostic text")

    def test_disappeared_finding_resolves_then_reappearing_finding_reopens(self):
        first = scan_findings(self.repo)
        fid = first["findings"][0]["id"]
        self.live.clear()
        self.assertEqual(scan_findings(self.repo)["auto_resolved"], 1)
        self.live.append(finding())
        result = scan_findings(self.repo)
        self.assertEqual(result["reopened"], 1)
        self.assertEqual(next(x for x in result["findings"] if x["id"] == fid)["state"], "open")

    def test_manual_resolution_requires_reason_and_live_scan_reopens(self):
        result = scan_findings(self.repo)
        fid = result["findings"][0]["id"]
        with self.assertRaises(ValueError):
            resolve_finding(self.repo, fid, "")
        resolve_finding(self.repo, fid, "Fixed by correcting input validation")
        self.assertEqual(scan_findings(self.repo)["reopened"], 1)

    def test_filtering_metrics_and_event_history(self):
        result = scan_findings(self.repo)
        fid = result["findings"][0]["id"]
        triage_finding(self.repo, fid, state="accepted", owner="security", priority="high", due_date="2099-01-01")
        self.assertEqual(list_findings(self.repo, state="accepted")["count"], 1)
        metrics = finding_metrics(self.repo)
        self.assertEqual(metrics["accepted_risk"], 1)
        self.assertEqual(metrics["open_by_priority"]["high"], 0)
        history = finding_history(self.repo, fid)
        self.assertGreaterEqual(history["count"], 2)
        self.assertEqual(history["events"][0]["event"], "finding_triaged")

    def test_journal_tampering_is_detected(self):
        scan_findings(self.repo)
        journal = self.repo / ".steadfast" / "finding-events.jsonl"
        journal.write_text(journal.read_text(encoding="utf-8").replace("finding_opened", "finding_forged"))
        with self.assertRaisesRegex(ValueError, "hash invalid"):
            finding_history(self.repo)

    def test_path_and_due_date_validation(self):
        result = scan_findings(self.repo)
        fid = result["findings"][0]["id"]
        with self.assertRaisesRegex(ValueError, "YYYY-MM-DD"):
            triage_finding(self.repo, fid, due_date="tomorrow")
        with self.assertRaisesRegex(ValueError, "not found"):
            triage_finding(self.repo, "../escape")

if __name__ == "__main__":
    unittest.main()
