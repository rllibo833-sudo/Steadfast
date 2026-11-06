from __future__ import annotations

import re
from collections import defaultdict
from typing import Any


_STOPWORDS = {
    "a", "about", "across", "an", "and", "are", "as", "at", "by", "for",
    "from", "in", "into", "is", "it", "of", "on", "or", "the", "their",
    "this", "to", "with", "without", "yang", "dan", "untuk", "dari",
    "dengan", "pada", "atau", "di",
}
_WORD = re.compile(r"[^\W_]+", re.UNICODE)


def _extract_terms(text: str) -> list[dict[str, Any]]:
    """Extract deterministic lexical terms and adjacent phrases with exact character spans."""
    matches = [
        match for match in _WORD.finditer(text.casefold())
        if len(match.group()) >= 3 and match.group() not in _STOPWORDS
    ]
    terms: dict[str, dict[str, Any]] = {}
    for match in matches:
        term = match.group()
        terms.setdefault(term, {
            "term": term,
            "start": match.start(),
            "end": match.end(),
            "surface": text[match.start():match.end()],
            "method": "normalized_token_v1",
        })
    # Adjacent two/three-token phrases preserve useful compound concepts.
    for width in (2, 3):
        for index in range(len(matches) - width + 1):
            window = matches[index:index + width]
            if any(
                matches[k + 1].start() > matches[k].end() + 1
                for k in range(index, index + width - 1)
            ):
                continue
            phrase = " ".join(item.group() for item in window)
            if phrase not in terms:
                start, end = window[0].start(), window[-1].end()
                terms[phrase] = {
                    "term": phrase,
                    "start": start,
                    "end": end,
                    "surface": text[start:end],
                    "method": f"adjacent_{width}gram_v1",
                }
    return [terms[key] for key in sorted(terms)]


def infer_candidate_relations(
    manifest: dict[str, Any],
    *,
    threshold: float = 0.2,
) -> dict[str, Any]:
    """Extract review-only lexical concepts and candidate project relations.

    This is a deterministic symbolic baseline, not semantic NCM. It never edits
    manifest facts and never promotes candidates to verified relationships.
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

    project_terms: dict[str, set[str]] = {}
    concept_evidence: dict[str, list[dict[str, Any]]] = defaultdict(list)
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []

    for project in projects:
        project_id = project["id"]
        purpose = project["purpose"]
        project_node = f"project:{project_id}"
        terms = _extract_terms(purpose)
        project_terms[project_id] = {item["term"] for item in terms}
        nodes.append({
            "id": project_node,
            "kind": "project",
            "label": project.get("name", project_id),
            "attributes": {"status": project.get("status", "unverified")},
            "provenance": {"manifest_field": f"projects[{project_id}]"},
        })
        for term in terms:
            concept_id = f"concept:{term['term']}"
            concept_evidence[term["term"]].append({
                "project_id": project_id,
                "field": f"projects[{project_id}].purpose",
                "start": term["start"],
                "end": term["end"],
                "surface": term["surface"],
                "method": term["method"],
            })
            edges.append({
                "from": project_node,
                "to": concept_id,
                "type": "mentions_candidate_concept",
                "attributes": {
                    "extraction_method": term["method"],
                    "character_start": term["start"],
                    "character_end": term["end"],
                    "surface": term["surface"],
                },
                "evidence": f"projects[{project_id}].purpose:{term['start']}:{term['end']}",
                "epistemic_status": "candidate",
            })

    for term in sorted(concept_evidence):
        evidence = concept_evidence[term]
        nodes.append({
            "id": f"concept:{term}",
            "kind": "candidate_concept",
            "label": term,
            "attributes": {
                "extraction": "lexical",
                "mention_count": len(evidence),
                "project_count": len({item["project_id"] for item in evidence}),
            },
            "provenance": {"mentions": evidence},
        })

    declared_pairs: dict[frozenset[str], list[dict[str, Any]]] = defaultdict(list)
    for index, relation in enumerate(manifest.get("relationships", [])):
        if not isinstance(relation, dict):
            continue
        left, right = relation.get("from"), relation.get("to")
        if isinstance(left, str) and isinstance(right, str):
            declared_pairs[frozenset((left, right))].append({
                "index": index,
                "type": relation.get("type"),
                "status": relation.get("status"),
            })

    review_queue: list[dict[str, Any]] = []
    project_ids = sorted(project_terms)
    for index, left in enumerate(project_ids):
        for right in project_ids[index + 1:]:
            left_terms, right_terms = project_terms[left], project_terms[right]
            shared = sorted(left_terms & right_terms)
            union = left_terms | right_terms
            score = len(shared) / len(union) if union else 0.0
            if not shared or score < threshold:
                continue
            declared = declared_pairs.get(frozenset((left, right)), [])
            candidate = {
                "from": f"project:{left}",
                "to": f"project:{right}",
                "type": "lexical_purpose_overlap",
                "attributes": {
                    "method": "token_jaccard_v2",
                    "score": round(score, 6),
                    "threshold": threshold,
                    "shared_terms": shared,
                    "interpretation": "lexical_overlap_only_not_a_verified_dependency",
                },
                "evidence": f"projects[{left}].purpose|projects[{right}].purpose",
                "epistemic_status": "candidate",
            }
            edges.append(candidate)
            review_queue.append({
                "candidate_edge": candidate,
                "reconciliation": (
                    "declared_pair_exists" if declared else "no_matching_declared_pair"
                ),
                "matching_manifest_relationships": declared,
                "review_required": True,
                "note": (
                    "A declared pair is not proof that this lexical relation is correct."
                    if declared else
                    "No matching declared pair was found; this is not evidence of contradiction."
                ),
            })

    return {
        "model_version": "1.2.0-experimental",
        "model_type": "ncm_concept_graph_projection",
        "source_manifest": {
            "universe_id": manifest.get("universe_id"),
            "manifest_version": manifest.get("manifest_version"),
        },
        "semantics": {
            "purpose": "Extract lexical candidate concepts and candidate project overlaps for human review.",
            "inference_performed": True,
            "inference_method": "lexical_extraction_and_token_jaccard_v2",
            "semantic_understanding": False,
            "relationships_are_verified": False,
            "project_sources_are_live_checked": False,
            "source_text_is_preserved": True,
        },
        "summary": {
            "projects": len(projects),
            "source_systems": 0,
            "declared_concepts": 0,
            "candidate_concepts": len(concept_evidence),
            "audit_findings": 0,
            "edges": len(edges),
            "candidate_relations": len(review_queue),
            "review_items": len(review_queue),
        },
        "nodes": nodes,
        "edges": edges,
        "review_queue": review_queue,
    }
