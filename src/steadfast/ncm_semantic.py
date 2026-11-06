from __future__ import annotations

import hashlib
import json
import os
import urllib.error
import urllib.request
from typing import Any, Mapping


def _digest(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _evidence_index(manifest: dict[str, Any]) -> dict[str, str]:
    index: dict[str, str] = {}
    for project in manifest.get("projects", []):
        if not isinstance(project, dict) or not isinstance(project.get("id"), str):
            continue
        project_id = project["id"]
        for field in ("name", "purpose", "status"):
            value = project.get(field)
            if isinstance(value, str) and value.strip():
                index[f"projects[{project_id}].{field}"] = value
        for number, ref in enumerate(project.get("sources", []) if isinstance(project.get("sources"), list) else []):
            if not isinstance(ref, dict):
                continue
            for field in ("title", "role", "status", "uri"):
                value = ref.get(field)
                if isinstance(value, str) and value.strip():
                    index[f"projects[{project_id}].sources[{number}].{field}"] = value
    return index


def _call_model(manifest: dict[str, Any], env: Mapping[str, str]) -> dict[str, Any]:
    api_key = env.get("NCM_API_KEY", "").strip()
    base_url = env.get("NCM_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    model = env.get("NCM_MODEL", "").strip()
    if not api_key or not model:
        raise RuntimeError("NCM_API_KEY and NCM_MODEL must be configured.")
    projects = [
        {key: item.get(key) for key in ("id", "name", "purpose", "status", "sources")}
        for item in manifest.get("projects", [])
        if isinstance(item, dict)
    ]
    payload = {
        "model": model,
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a cautious cross-project concept analyst. Return one JSON object with keys "
                    "concepts, relations, and possible_conflicts. Do not invent facts. Every evidence item "
                    "must contain path and quote copied verbatim from the supplied manifest. Concepts: "
                    "{id,name,definition,evidence:[{path,quote}]}. Relations: "
                    "{from,to,type,rationale,confidence,evidence:[{path,quote}]}. "
                    "Conflicts: {claim_a,claim_b,reason,evidence:[{path,quote}]}. "
                    "Only project IDs supplied may be relation endpoints. Keep all outputs hypothetical."
                ),
            },
            {
                "role": "user",
                "content": json.dumps({
                    "universe_id": manifest.get("universe_id"),
                    "manifest_version": manifest.get("manifest_version"),
                    "projects": projects,
                    "relationships": manifest.get("relationships", []),
                }, ensure_ascii=False),
            },
        ],
    }
    request = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            result = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, ValueError) as exc:
        raise RuntimeError(f"Semantic model request failed: {type(exc).__name__}") from None
    try:
        content = result["choices"][0]["message"]["content"]
        parsed = json.loads(content)
    except (KeyError, IndexError, TypeError, json.JSONDecodeError):
        raise RuntimeError("Semantic model returned an invalid JSON response.") from None
    if not isinstance(parsed, dict):
        raise RuntimeError("Semantic model response must be a JSON object.")
    return parsed


def _validate_candidates(
    response: dict[str, Any],
    manifest: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    evidence_index = _evidence_index(manifest)
    project_ids = {
        item["id"] for item in manifest.get("projects", [])
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    findings: list[dict[str, Any]] = []

    def evidence_valid(items: Any, path: str) -> bool:
        if not isinstance(items, list) or not items:
            return False
        for item in items:
            if not isinstance(item, dict):
                return False
            source = evidence_index.get(item.get("path"))
            quote = item.get("quote")
            if not isinstance(source, str) or not isinstance(quote, str) or not quote.strip() or quote not in source:
                return False
        return True

    concepts = []
    for index, item in enumerate(response.get("concepts", []) if isinstance(response.get("concepts"), list) else []):
        if not isinstance(item, dict) or not all(isinstance(item.get(key), str) and item[key].strip() for key in ("name", "definition")):
            findings.append({"code": "INVALID_CONCEPT", "item": index})
            continue
        if not evidence_valid(item.get("evidence"), f"concepts[{index}]"):
            findings.append({"code": "UNSUPPORTED_CONCEPT_EVIDENCE", "item": index})
            continue
        concepts.append({
            "id": f"candidate-concept:{hashlib.sha256(item['name'].casefold().encode()).hexdigest()[:16]}",
            "name": item["name"].strip(),
            "definition": item["definition"].strip(),
            "evidence": item["evidence"],
            "epistemic_status": "candidate",
        })

    relations = []
    for index, item in enumerate(response.get("relations", []) if isinstance(response.get("relations"), list) else []):
        if (
            not isinstance(item, dict)
            or not isinstance(item.get("from"), str)
            or not isinstance(item.get("to"), str)
            or item.get("from") not in project_ids
            or item.get("to") not in project_ids
            or item.get("from") == item.get("to")
        ):
            findings.append({"code": "INVALID_RELATION_ENDPOINT", "item": index})
            continue
        confidence = item.get("confidence")
        if not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
            findings.append({"code": "INVALID_RELATION_CONFIDENCE", "item": index})
            continue
        if not isinstance(item.get("type"), str) or not isinstance(item.get("rationale"), str) or not evidence_valid(item.get("evidence"), f"relations[{index}]"):
            findings.append({"code": "UNSUPPORTED_RELATION_EVIDENCE", "item": index})
            continue
        relations.append({
            "from": f"project:{item['from']}",
            "to": f"project:{item['to']}",
            "type": item["type"].strip(),
            "rationale": item["rationale"].strip(),
            "confidence": round(float(confidence), 4),
            "evidence": item["evidence"],
            "epistemic_status": "candidate",
        })

    conflicts = []
    for index, item in enumerate(response.get("possible_conflicts", []) if isinstance(response.get("possible_conflicts"), list) else []):
        if not isinstance(item, dict) or not isinstance(item.get("reason"), str) or not evidence_valid(item.get("evidence"), f"possible_conflicts[{index}]"):
            findings.append({"code": "UNSUPPORTED_CONFLICT_EVIDENCE", "item": index})
            continue
        conflicts.append({
            "claim_a": str(item.get("claim_a", "")),
            "claim_b": str(item.get("claim_b", "")),
            "reason": item["reason"].strip(),
            "evidence": item["evidence"],
            "epistemic_status": "candidate",
            "review_required": True,
        })
    return concepts, relations, conflicts, findings


def infer_semantic_candidates(
    manifest: dict[str, Any],
    *,
    allow_remote: bool = False,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Run opt-in semantic analysis; every generated assertion remains a candidate."""
    digest = _digest(manifest)
    if not allow_remote:
        return {
            "status": "blocked",
            "reason": "remote_model_data_transfer_requires_explicit_approval",
            "source_manifest_sha256": digest,
            "safety": {"remote_request_made": False, "manifest_modified": False, "candidates_promoted": False},
        }
    settings = os.environ if env is None else env
    if not settings.get("NCM_API_KEY", "").strip() or not settings.get("NCM_MODEL", "").strip():
        return {
            "status": "failed",
            "error": "NCM_API_KEY and NCM_MODEL must be configured.",
            "source_manifest_sha256": digest,
            "safety": {"remote_request_made": False, "manifest_modified": False, "candidates_promoted": False},
        }
    try:
        response = _call_model(manifest, settings)
    except RuntimeError as exc:
        return {
            "status": "failed",
            "error": str(exc),
            "source_manifest_sha256": digest,
            "safety": {"remote_request_made": True, "manifest_modified": False, "candidates_promoted": False},
        }
    concepts, relations, conflicts, findings = _validate_candidates(response, manifest)
    return {
        "status": "completed",
        "model_type": "evidence_grounded_semantic_candidates",
        "source_manifest_sha256": digest,
        "provider": {"base_url": settings.get("NCM_BASE_URL", "https://api.openai.com/v1"), "model": settings.get("NCM_MODEL")},
        "summary": {
            "concepts": len(concepts),
            "relations": len(relations),
            "possible_conflicts": len(conflicts),
            "rejected_items": len(findings),
        },
        "concepts": concepts,
        "relations": relations,
        "possible_conflicts": conflicts,
        "findings": findings,
        "safety": {
            "remote_request_made": True,
            "manifest_modified": False,
            "candidates_promoted": False,
            "evidence_quotes_verified_against_manifest": True,
        },
    }


__all__ = ["infer_semantic_candidates"]
