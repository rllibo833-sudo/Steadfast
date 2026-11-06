from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any


def model_digest(model: dict[str, Any]) -> str:
    canonical = json.dumps(model, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def validate_review_ledger(
    model: dict[str, Any],
    ledger: dict[str, Any],
) -> dict[str, Any]:
    """Validate human review decisions without promoting model assertions to facts."""
    findings: list[dict[str, Any]] = []
    if not isinstance(model, dict):
        return {"valid": False, "model_sha256": None, "summary": {}, "decisions": [], "findings": [{"code": "INVALID_MODEL", "message": "Model must be a JSON object"}], "safety": {"model_modified": False, "manifest_modified": False, "candidate_promoted_to_verified": False}}
    if not isinstance(ledger, dict):
        return {"valid": False, "model_sha256": model_digest(model), "summary": {}, "decisions": [], "findings": [{"code": "INVALID_REVIEW_LEDGER", "message": "Review ledger must be a JSON object"}], "safety": {"model_modified": False, "manifest_modified": False, "candidate_promoted_to_verified": False}}
    digest = model_digest(model)
    if ledger.get("schema_version") != "1.0.0":
        findings.append({"code": "UNSUPPORTED_REVIEW_SCHEMA", "message": "schema_version must be 1.0.0"})
    if ledger.get("model_sha256") != digest:
        findings.append({"code": "MODEL_DIGEST_MISMATCH", "message": "Review ledger targets a different model artifact"})

    reviewer = ledger.get("reviewer")
    reviewed_at = ledger.get("reviewed_at")
    if not isinstance(reviewer, str) or not reviewer.strip():
        findings.append({"code": "REVIEWER_REQUIRED", "message": "A non-empty reviewer is required"})
    timestamp_valid = False
    if not isinstance(reviewed_at, str) or not reviewed_at.strip():
        findings.append({"code": "REVIEW_TIMESTAMP_REQUIRED", "message": "A review timestamp is required"})
    else:
        try:
            parsed_timestamp = datetime.fromisoformat(reviewed_at.replace("Z", "+00:00"))
            timestamp_valid = parsed_timestamp.tzinfo is not None and parsed_timestamp.utcoffset() is not None
        except ValueError:
            timestamp_valid = False
        if not timestamp_valid:
            findings.append({"code": "INVALID_REVIEW_TIMESTAMP", "message": "reviewed_at must be an ISO-8601 timestamp with an explicit timezone"})

    model_edges = model.get("edges", [])
    if not isinstance(model_edges, list):
        findings.append({"code": "MODEL_EDGES_MUST_BE_ARRAY", "message": "model.edges must be an array"})
        model_edges = []
    edge_by_id = {
        edge.get("edge_id"): edge
        for edge in model_edges
        if isinstance(edge, dict) and isinstance(edge.get("edge_id"), str)
    }
    decisions = ledger.get("decisions", [])
    if not isinstance(decisions, list):
        findings.append({"code": "DECISIONS_MUST_BE_ARRAY", "message": "decisions must be an array"})
        decisions = []

    seen: set[str] = set()
    reviewed_candidates: set[str] = set()
    normalized: list[dict[str, Any]] = []
    for index, decision in enumerate(decisions):
        prefix = f"decisions[{index}]"
        if not isinstance(decision, dict):
            findings.append({"code": "INVALID_DECISION", "path": prefix, "message": "Decision must be an object"})
            continue
        edge_id = decision.get("edge_id")
        if not isinstance(edge_id, str) or edge_id not in edge_by_id:
            findings.append({"code": "UNKNOWN_EDGE_ID", "path": prefix, "message": "edge_id does not exist in the target model"})
            continue
        if edge_id in seen:
            findings.append({"code": "DUPLICATE_EDGE_DECISION", "path": prefix, "message": "Each edge may be reviewed once per ledger"})
            continue
        seen.add(edge_id)
        edge = edge_by_id[edge_id]
        if edge.get("epistemic_status") != "candidate":
            findings.append({"code": "NON_CANDIDATE_REVIEW", "path": prefix, "message": "Only candidate edges may receive this review decision"})
            continue
        outcome = decision.get("decision")
        if not isinstance(outcome, str) or outcome not in {"accepted", "rejected", "deferred"}:
            findings.append({"code": "INVALID_REVIEW_OUTCOME", "path": prefix, "message": "decision must be accepted, rejected, or deferred"})
            continue
        rationale = decision.get("rationale")
        evidence = decision.get("evidence")
        rationale_valid = isinstance(rationale, str) and bool(rationale.strip())
        evidence_valid = (
            isinstance(evidence, list)
            and bool(evidence)
            and all(isinstance(item, str) and item.strip() for item in evidence)
        )
        if not rationale_valid:
            findings.append({"code": "RATIONALE_REQUIRED", "path": prefix, "message": "A non-empty rationale is required"})
        if not evidence_valid:
            findings.append({"code": "REVIEW_EVIDENCE_REQUIRED", "path": prefix, "message": "At least one evidence reference is required"})
        if not rationale_valid or not evidence_valid:
            continue
        reviewed_candidates.add(edge_id)
        normalized.append({
            "edge_id": edge_id,
            "decision": outcome,
            "rationale": rationale.strip(),
            "evidence": sorted(set(item.strip() for item in evidence)),
            "reviewer": reviewer.strip() if isinstance(reviewer, str) else None,
            "reviewed_at": reviewed_at.strip() if isinstance(reviewed_at, str) else None,
            "epistemic_status_after_review": "candidate",
        })

    candidate_count = sum(1 for edge in model_edges if isinstance(edge, dict) and edge.get("epistemic_status") == "candidate")
    accepted = sum(item["decision"] == "accepted" for item in normalized)
    rejected = sum(item["decision"] == "rejected" for item in normalized)
    deferred = sum(item["decision"] == "deferred" for item in normalized)
    valid = not findings
    return {
        "valid": valid,
        "model_sha256": digest,
        "reviewer": reviewer if isinstance(reviewer, str) else None,
        "reviewed_at": reviewed_at if isinstance(reviewed_at, str) else None,
        "summary": {
            "candidate_edges": candidate_count,
            "decisions": len(normalized),
            "accepted": accepted,
            "rejected": rejected,
            "deferred": deferred,
            "pending": candidate_count - len(reviewed_candidates),
        },
        "decisions": normalized,
        "findings": findings,
        "safety": {
            "model_modified": False,
            "manifest_modified": False,
            "candidate_promoted_to_verified": False,
        },
    }
