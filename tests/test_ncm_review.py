import unittest

from steadfast.ncm_review import model_digest, validate_review_ledger


class NcmReviewTests(unittest.TestCase):
    def setUp(self):
        self.model = {
            "model_version": "1.3.0-experimental",
            "edges": [
                {"edge_id": "edge:" + "a" * 24, "epistemic_status": "candidate"},
                {"edge_id": "edge:" + "b" * 24, "epistemic_status": "manifest_asserted_not_independently_verified"},
            ],
        }
        self.ledger = {
            "schema_version": "1.0.0",
            "model_sha256": model_digest(self.model),
            "reviewer": "reviewer-1",
            "reviewed_at": "2026-11-07T10:00:00Z",
            "decisions": [{
                "edge_id": "edge:" + "a" * 24,
                "decision": "accepted",
                "rationale": "Reviewed against the linked project records.",
                "evidence": ["manifest://projects/alpha", "manifest://projects/beta"],
            }],
        }

    def test_valid_decision_is_evidence_bound_and_candidate_stays_candidate(self):
        result = validate_review_ledger(self.model, self.ledger)
        self.assertTrue(result["valid"])
        self.assertEqual(result["summary"]["accepted"], 1)
        self.assertEqual(result["decisions"][0]["epistemic_status_after_review"], "candidate")
        self.assertFalse(result["safety"]["candidate_promoted_to_verified"])

    def test_digest_mismatch_is_rejected(self):
        ledger = dict(self.ledger, model_sha256="0" * 64)
        result = validate_review_ledger(self.model, ledger)
        self.assertFalse(result["valid"])
        self.assertIn("MODEL_DIGEST_MISMATCH", {item["code"] for item in result["findings"]})

    def test_unknown_and_non_candidate_edges_are_rejected(self):
        ledger = dict(self.ledger, decisions=[
            dict(self.ledger["decisions"][0], edge_id="edge:" + "c" * 24),
            dict(self.ledger["decisions"][0], edge_id="edge:" + "b" * 24),
        ])
        result = validate_review_ledger(self.model, ledger)
        codes = {item["code"] for item in result["findings"]}
        self.assertIn("UNKNOWN_EDGE_ID", codes)
        self.assertIn("NON_CANDIDATE_REVIEW", codes)

    def test_duplicate_decisions_are_rejected(self):
        decision = self.ledger["decisions"][0]
        ledger = dict(self.ledger, decisions=[decision, decision])
        result = validate_review_ledger(self.model, ledger)
        self.assertIn("DUPLICATE_EDGE_DECISION", {item["code"] for item in result["findings"]})

    def test_non_object_ledger_is_rejected_safely(self):
        result = validate_review_ledger(self.model, [])
        self.assertFalse(result["valid"])
        self.assertIn("INVALID_REVIEW_LEDGER", {item["code"] for item in result["findings"]})

    def test_rationale_and_evidence_are_mandatory(self):
        decision = dict(self.ledger["decisions"][0], rationale="", evidence=[])
        result = validate_review_ledger(self.model, dict(self.ledger, decisions=[decision]))
        codes = {item["code"] for item in result["findings"]}
        self.assertIn("RATIONALE_REQUIRED", codes)
        self.assertIn("REVIEW_EVIDENCE_REQUIRED", codes)


if __name__ == "__main__":
    unittest.main()
