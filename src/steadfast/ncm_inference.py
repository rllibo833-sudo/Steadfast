from __future__ import annotations

import re
from typing import Any


_STOPWORDS = {
    "about", "across", "agent", "and", "are", "for", "from", "into", "its",
    "project", "system", "the", "their", "this", "with", "without",
}


def _tokens(value: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]+", value.casefold())
        if len(token) >= 3 and token not in _STOPWORDS
    }


def infer_candidate_relations(
    manifest: dict[str, Any],
    *,
    threshold: float = 0.2,
) -> dict[str, Any]:
    """Emit read-only lexical-overlap candidates; this is not semantic NCM inference.

    Scores are Jaccard(token-set) similarities over declared project purposes.
    Every edge remains epistemic_status='candidate' and cites both manifest fields.
    """
    if not 0.0 <= threshold <= 1.0:
        raise ValueError("threshold must be between 0.0 and 1.0")

    projects = [
        item for item in manifest.get("projects", [])
        if isinstance(item, dict)
        and isinstance(item.get("id"), str)
        and isinstance(item.get("purpose"), str)
        and item["purpose"].strip()
    ]
    projects.sort(key=lambda item: item["id"])
    token_sets = {item["id"]: _tokens(item["purpose"]) for item in projects}
    candidates: list[dict[str, Any]] = []

    for index, left in enumerate(projects):
        left_id = left["id"]
        left_tokens = token_sets[left_id]
        if not left_tokens:
            continue
        for right in projects[index + 1:]:
            right_id = right["id"]
            right_tokens = token_sets[right_id]
            union = left_tokens | right_tokens
            if not union:
                continue
            shared = sorted(left_tokens & right_tokens)
            score = len(shared) / len(union)
            if score < threshold or not shared:
                continue
            candidates.append({
                "from": f"project:{left_id}",
                "to": f"project:{right_id}",
                "type": "lexical_purpose_overlap",
                "attributes": {
                    "method": "token_jaccard_v1",
                    "score": round(score, 6),
                    "threshold": threshold,
                    "shared_terms": shared,
                    "interpretation": "lexical_overlap_only_not_a_verified_dependency",
                },
                "evidence": (
                    f"projects[{left_id}].purpose|projects[{right_id}].purpose"
                ),
                "epistemic_status": "candidate",
            })

    return {
        "model_version": "1.1.0-experimental",
        "model_type": "ncm_concept_graph_projection",
        "source_manifest": {
            "universe_id": manifest.get("universe_id"),
            "manifest_version": manifest.get("manifest_version"),
        },
        "semantics": {
            "purpose": "Generate review-only relation candidates from declared project purpose text.",
            "inference_performed": True,
            "inference_method": "token_jaccard_v1",
            "semantic_understanding": False,
            "relationships_are_verified": False,
            "project_sources_are_live_checked": False,
            "source_text_is_preserved": True,
        },
        "summary": {
            "projects": len(projects),
            "source_systems": 0,
            "declared_concepts": 0,
            "audit_findings": 0,
            "edges": len(candidates),
            "candidate_relations": len(candidates),
        },
        "nodes": [],
        "edges": candidates,
    }
