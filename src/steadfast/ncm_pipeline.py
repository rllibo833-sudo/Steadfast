from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from typing import Any


_STOPWORDS = {
    "a", "about", "across", "an", "and", "are", "as", "at", "by", "for",
    "from", "in", "into", "is", "it", "of", "on", "or", "the", "their",
    "this", "to", "with", "without", "yang", "dan", "untuk", "dari",
    "dengan", "pada", "atau", "di", "ini", "itu", "dalam", "sebagai",
}
_WORD = re.compile(r"[^\W_]+", re.UNICODE)


def _extract_terms(text: str) -> list[dict[str, Any]]:
    """Extract normalized tokens and adjacent phrases with original character spans."""
    matches = [
        match for match in _WORD.finditer(text)
        if len(match.group().casefold()) >= 3 and match.group().casefold() not in _STOPWORDS
    ]
    terms: dict[str, dict[str, Any]] = {}
    for match in matches:
        term = match.group().casefold()
        terms.setdefault(term, {
            "term": term, "start": match.start(), "end": match.end(),
            "surface": text[match.start():match.end()], "method": "normalized_token_v1",
        })
    for width in (2, 3):
        for index in range(len(matches) - width + 1):
            window = matches[index:index + width]
            if any(
                not text[matches[k].end():matches[k + 1].start()].isspace()
                for k in range(index, index + width - 1)
            ):
                continue
            phrase = " ".join(item.group().casefold() for item in window)
            if phrase not in terms:
                start, end = window[0].start(), window[-1].end()
                terms[phrase] = {
                    "term": phrase, "start": start, "end": end,
                    "surface": text[start:end], "method": f"adjacent_{width}gram_v1",
                }
    return [terms[key] for key in sorted(terms)]


def _text_fields(value: Any, prefix: str) -> list[tuple[str, str]]:
    """Return explicitly selected descriptive fields; never stringify arbitrary objects."""
    if not isinstance(value, dict):
        return []
    result: list[tuple[str, str]] = []
    for key in ("name", "title", "purpose", "role", "evidence", "scope", "description"):
        text = value.get(key)
        if isinstance(text, str) and text.strip():
            result.append((f"{prefix}.{key}", text))
    return result


def infer_candidate_relations(
    manifest: dict[str, Any],
    *,
    threshold: float = 0.2,
) -> dict[str, Any]:
    """Build a deterministic, read-only lexical concept graph for human review.

    This is a symbolic discovery baseline, not semantic NCM. All generated
    concepts and relations remain candidates and retain field-level provenance.
    """
    if not 0.0 <= threshold <= 1.0:
        raise ValueError("threshold must be between 0.0 and 1.0")

    projects = [
        item for item in manifest.get("projects", [])
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    ]
    projects.sort(key=lambda item: item["id"])
    sources = [item for item in manifest.get("sources", []) if isinstance(item, dict) and isinstance(item.get("id"), str)]
    consumers = [item for item in manifest.get("consumers", []) if isinstance(item, dict) and isinstance(item.get("id"), str)]

    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    concept_evidence: dict[str, list[dict[str, Any]]] = defaultdict(list)
    project_terms: dict[str, set[str]] = defaultdict(set)
    project_text_fields: dict[str, list[str]] = defaultdict(list)
    source_ids = {item["id"] for item in sources}

    def add_text(owner_id: str, field: str, text: str, *, project_id: str | None = None) -> None:
        for term in _extract_terms(text):
            concept = term["term"]
            concept_id = f"concept:{concept}"
            evidence = {
                "owner_id": owner_id,
                "field": field,
                "start": term["start"],
                "end": term["end"],
                "surface": term["surface"],
                "method": term["method"],
            }
            if project_id is not None:
                evidence["project_id"] = project_id
                project_terms[project_id].add(concept)
                project_text_fields[project_id].append(field)
            concept_evidence[concept].append(evidence)
            edges.append({
                "from": owner_id,
                "to": concept_id,
                "type": "mentions_candidate_concept",
                "attributes": {
                    "extraction_method": term["method"],
                    "character_start": term["start"],
                    "character_end": term["end"],
                    "surface": term["surface"],
                },
                "evidence": f"{field}:{term['start']}:{term['end']}",
                "epistemic_status": "candidate",
            })

    for source in sorted(sources, key=lambda item: item["id"]):
        source_id = source["id"]
        nodes.append({
            "id": f"source:{source_id}", "kind": "source_system",
            "label": source.get("type", source_id),
            "attributes": {"state": source.get("state", "unknown")},
            "provenance": {"manifest_field": f"sources[{source_id}]"},
        })
        for field, text in _text_fields(source, f"sources[{source_id}]"):
            add_text(f"source:{source_id}", field, text)

    for consumer in sorted(consumers, key=lambda item: item["id"]):
        consumer_id = consumer["id"]
        nodes.append({
            "id": f"consumer:{consumer_id}", "kind": "consumer",
            "label": consumer.get("name", consumer_id),
            "attributes": {"implementation_status": consumer.get("implementation_status", "unknown")},
            "provenance": {"manifest_field": f"consumers[{consumer_id}]"},
        })
        for field, text in _text_fields(consumer, f"consumers[{consumer_id}]"):
            add_text(f"consumer:{consumer_id}", field, text)

    for project in projects:
        project_id = project["id"]
        project_node = f"project:{project_id}"
        nodes.append({
            "id": project_node, "kind": "project",
            "label": project.get("name", project_id),
            "attributes": {"status": project.get("status", "unverified")},
            "provenance": {"manifest_field": f"projects[{project_id}]"},
        })
        for field, text in _text_fields(project, f"projects[{project_id}]"):
            add_text(project_node, field, text, project_id=project_id)

        project_sources = project.get("sources", [])
        if isinstance(project_sources, list):
            for index, reference in enumerate(project_sources):
                if not isinstance(reference, dict):
                    continue
                source_id = reference.get("source_id")
                if not isinstance(source_id, str):
                    continue
                if source_id not in source_ids:
                    # Preserve the unresolved reference as a finding-like candidate node.
                    missing_id = f"source-reference:{project_id}:{index}"
                    nodes.append({
                        "id": missing_id, "kind": "unresolved_source_reference",
                        "label": source_id, "attributes": {"uri": reference.get("uri")},
                        "provenance": {"manifest_field": f"projects[{project_id}].sources[{index}]"},
                    })
                    edges.append({
                        "from": project_node, "to": missing_id, "type": "references_unresolved_source",
                        "attributes": {}, "evidence": f"projects[{project_id}].sources[{index}]",
                        "epistemic_status": "candidate",
                    })
                    continue
                edges.append({
                    "from": project_node, "to": f"source:{source_id}", "type": "uses_source_system",
                    "attributes": {
                        "role": reference.get("role"),
                        "uri": reference.get("uri"),
                        "status": reference.get("status", "unknown"),
                    },
                    "evidence": f"projects[{project_id}].sources[{index}]",
                    "epistemic_status": "manifest_asserted_not_independently_verified",
                })
                for key in ("role", "title", "evidence"):
                    value = reference.get(key)
                    if isinstance(value, str) and value.strip():
                        add_text(project_node, f"projects[{project_id}].sources[{index}].{key}", value, project_id=project_id)

    if isinstance(manifest.get("inventory_notes"), list):
        nodes.append({
            "id": "universe:inventory", "kind": "universe_inventory",
            "label": manifest.get("title", "Universe inventory"), "attributes": {},
            "provenance": {"manifest_field": "inventory_notes"},
        })
    for note_index, note in enumerate(manifest.get("inventory_notes", [])):
        if isinstance(note, str) and note.strip():
            add_text("universe:inventory", f"inventory_notes[{note_index}]", note)

    for concept in sorted(concept_evidence):
        mentions = concept_evidence[concept]
        unique_projects = sorted({item["project_id"] for item in mentions if "project_id" in item})
        nodes.append({
            "id": f"concept:{concept}", "kind": "candidate_concept",
            "label": concept,
            "attributes": {
                "extraction": "lexical",
                "mention_count": len(mentions),
                "project_count": len(unique_projects),
                "owner_count": len({item["owner_id"] for item in mentions}),
            },
            "provenance": {"mentions": mentions},
        })

    # Preserve every declared manifest relationship as an explicit graph edge.
    # These are source assertions, not independently verified facts.
    endpoint_node_ids = {
        item["id"]: f"project:{item['id']}"
        for item in projects
    }
    endpoint_node_ids.update({
        item["id"]: f"consumer:{item['id']}"
        for item in consumers
    })
    endpoint_node_ids.update({
        item["id"]: f"source:{item['id']}"
        for item in sources
    })
    unresolved_endpoints: set[str] = set()
    manifest_findings: list[dict[str, Any]] = []
    declared_relationship_count = 0
    raw_relationships = manifest.get("relationships", [])
    if not isinstance(raw_relationships, list):
        manifest_findings.append({
            "code": "RELATIONSHIPS_MUST_BE_ARRAY",
            "message": "manifest.relationships must be an array",
        })
        raw_relationships = []
    for relation_index, relation in enumerate(raw_relationships):
        if not isinstance(relation, dict):
            manifest_findings.append({
                "code": "INVALID_MANIFEST_RELATIONSHIP",
                "relationship_index": relation_index,
                "message": "Relationship entry must be an object",
            })
            continue
        left, right = relation.get("from"), relation.get("to")
        if not isinstance(left, str) or not left.strip() or not isinstance(right, str) or not right.strip():
            manifest_findings.append({
                "code": "INVALID_MANIFEST_RELATIONSHIP_ENDPOINT",
                "relationship_index": relation_index,
                "from": left if isinstance(left, str) else None,
                "to": right if isinstance(right, str) else None,
                "message": "Relationship requires non-empty string from and to endpoints",
            })
            continue
        endpoint_ids: list[str] = []
        for endpoint in (left, right):
            node_id = endpoint_node_ids.get(endpoint)
            if node_id is None:
                node_id = f"unresolved-entity:{endpoint}"
                if node_id not in unresolved_endpoints:
                    unresolved_endpoints.add(node_id)
                    manifest_findings.append({
                        "code": "UNRESOLVED_MANIFEST_ENDPOINT",
                        "relationship_index": relation_index,
                        "endpoint": endpoint,
                        "node_id": node_id,
                        "message": "Declared relationship endpoint does not resolve to a project, source, or consumer",
                    })
                    nodes.append({
                        "id": node_id,
                        "kind": "unresolved_manifest_endpoint",
                        "label": endpoint,
                        "attributes": {},
                        "provenance": {"manifest_field": f"relationships[{relation_index}]"},
                    })
            endpoint_ids.append(node_id)
        edges.append({
            "from": endpoint_ids[0],
            "to": endpoint_ids[1],
            "type": "manifest_declared_relationship",
            "attributes": {
                "declared_type": relation.get("type"),
                "declared_status": relation.get("status", "unknown"),
            },
            "evidence": f"relationships[{relation_index}]",
            "epistemic_status": "manifest_asserted_not_independently_verified",
        })
        declared_relationship_count += 1

    declared_pairs: dict[frozenset[str], list[dict[str, Any]]] = defaultdict(list)
    for index, relation in enumerate(manifest.get("relationships", [])):
        if isinstance(relation, dict):
            left, right = relation.get("from"), relation.get("to")
            if isinstance(left, str) and isinstance(right, str):
                declared_pairs[frozenset((left, right))].append({
                    "index": index, "type": relation.get("type"), "status": relation.get("status"),
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
                "from": f"project:{left}", "to": f"project:{right}",
                "type": "lexical_project_overlap",
                "attributes": {
                    "method": "token_jaccard_v3", "score": round(score, 6),
                    "threshold": threshold, "shared_terms": shared,
                    "interpretation": "lexical_overlap_only_not_a_verified_dependency",
                },
                "evidence": json.dumps({
                    "left_fields": sorted(set(project_text_fields[left])),
                    "right_fields": sorted(set(project_text_fields[right])),
                    "shared_terms": shared,
                }, ensure_ascii=False, sort_keys=True),
                "epistemic_status": "candidate",
            }
            edges.append(candidate)
            review_queue.append({
                "candidate_edge": candidate,
                "reconciliation": "declared_pair_exists" if declared else "no_matching_declared_pair",
                "matching_manifest_relationships": declared,
                "review_required": True,
                "note": (
                    "A declared pair is not proof that this lexical relation is correct."
                    if declared else
                    "No matching declared pair was found; this is not evidence of contradiction."
                ),
            })

    for edge in edges:
        identity = {key: edge.get(key) for key in ("from", "to", "type", "attributes", "evidence")}
        canonical = json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        edge["edge_id"] = "edge:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:24]

    node_ids = {node["id"] for node in nodes}
    graph_findings = []
    for edge_index, edge in enumerate(edges):
        if edge["from"] not in node_ids or edge["to"] not in node_ids:
            graph_findings.append({
                "code": "DANGLING_GRAPH_EDGE", "edge_index": edge_index,
                "from": edge["from"], "to": edge["to"],
            })

    return {
        "model_version": "1.3.0-experimental",
        "model_type": "ncm_concept_graph_projection",
        "source_manifest": {
            "universe_id": manifest.get("universe_id"),
            "manifest_version": manifest.get("manifest_version"),
        },
        "semantics": {
            "purpose": "Extract candidate concepts from selected manifest text fields and propose project overlaps for review.",
            "inference_performed": True,
            "inference_method": "multifield_lexical_extraction_and_token_jaccard_v3",
            "semantic_understanding": False,
            "relationships_are_verified": False,
            "project_sources_are_live_checked": False,
            "source_text_is_preserved": True,
            "remote_sources_read": False,
            "canonical_manifest_modified": False,
        },
        "summary": {
            "projects": len(projects), "source_systems": len(sources),
            "consumers": len(consumers), "declared_relationships": declared_relationship_count, "declared_concepts": 0,
            "candidate_concepts": len(concept_evidence),
            "audit_findings": len(graph_findings) + len(manifest_findings), "edges": len(edges),
            "candidate_relations": len(review_queue), "review_items": len(review_queue),
        },
        "nodes": nodes,
        "edges": edges,
        "review_queue": review_queue,
        "graph_findings": graph_findings,
        "manifest_findings": manifest_findings,
    }
