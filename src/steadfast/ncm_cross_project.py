from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from typing import Any

from .ncm_pipeline import _extract_terms, infer_candidate_relations


def _canonical_digest(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def build_cross_project_model(
    manifest: dict[str, Any],
    source_documents: list[dict[str, Any]] | None = None,
    *,
    threshold: float = 0.2,
) -> dict[str, Any]:
    """Build a deterministic cross-project graph from the manifest and bounded snapshots.

    Source documents are inputs only: this function performs no network or filesystem
    access, stores no full document text in the graph, and never promotes candidates.
    """
    if not isinstance(manifest, dict):
        raise ValueError("manifest must be an object")
    if not 0.0 <= threshold <= 1.0:
        raise ValueError("threshold must be between 0.0 and 1.0")
    if source_documents is not None and not isinstance(source_documents, list):
        raise ValueError("source_documents must be an array")

    model = infer_candidate_relations(manifest, threshold=threshold)
    nodes = model["nodes"]
    edges = model["edges"]
    node_by_id = {node["id"]: node for node in nodes}
    projects = {
        item["id"]: item for item in manifest.get("projects", [])
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    declared_source_ids = {
        item["id"] for item in manifest.get("sources", [])
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    project_source_ids: dict[str, set[str]] = defaultdict(set)
    for project_id, project in projects.items():
        refs = project.get("sources", [])
        if isinstance(refs, list):
            for ref in refs:
                if isinstance(ref, dict) and ref.get("source_id") in declared_source_ids:
                    project_source_ids[project_id].add(ref["source_id"])

    findings: list[dict[str, Any]] = []
    document_records: list[dict[str, Any]] = []
    concept_projects: dict[str, set[str]] = defaultdict(set)
    concept_evidence: dict[str, list[dict[str, Any]]] = defaultdict(list)
    seen_documents: set[str] = set()
    total_chars = 0

    # Seed cross-project membership with concepts already extracted from manifest fields.
    for node in nodes:
        if node.get("kind") != "candidate_concept":
            continue
        label = node.get("label")
        if not isinstance(label, str):
            continue
        concept_id = node.get("id")
        provenance = node.get("provenance", {})
        mentions = provenance.get("mentions", []) if isinstance(provenance, dict) else []
        for mention in mentions if isinstance(mentions, list) else []:
            if not isinstance(mention, dict):
                continue
            project_id = mention.get("project_id")
            if isinstance(project_id, str) and project_id in projects:
                concept_projects[label].add(project_id)
                concept_evidence[label].append({
                    "kind": "manifest_text",
                    "project_id": project_id,
                    "owner_id": mention.get("owner_id"),
                    "field": mention.get("field"),
                    "start": mention.get("start"),
                    "end": mention.get("end"),
                    "surface": mention.get("surface"),
                    "method": mention.get("method"),
                })

    for index, document in enumerate(source_documents or []):
        path = f"source_documents[{index}]"
        if not isinstance(document, dict):
            findings.append({"code": "INVALID_SOURCE_DOCUMENT", "path": path})
            continue
        document_id = document.get("document_id")
        project_id = document.get("project_id")
        source_id = document.get("source_id")
        content = document.get("content")
        if isinstance(source_id, str) and source_id not in declared_source_ids:
            findings.append({
                "code": "UNRESOLVED_DOCUMENT_SOURCE",
                "path": path,
                "document_id": document_id if isinstance(document_id, str) else None,
                "source_id": source_id,
            })
        status = document.get("status", "unknown")
        if not isinstance(document_id, str) or not document_id.strip():
            findings.append({"code": "DOCUMENT_ID_REQUIRED", "path": path})
            continue
        if document_id in seen_documents:
            findings.append({"code": "DUPLICATE_DOCUMENT_ID", "path": path, "document_id": document_id})
            continue
        seen_documents.add(document_id)
        if not isinstance(project_id, str) or project_id not in projects:
            findings.append({
                "code": "UNRESOLVED_DOCUMENT_PROJECT",
                "path": path,
                "document_id": document_id,
                "project_id": project_id if isinstance(project_id, str) else None,
            })
            continue
        if status not in {"read", "partial"}:
            findings.append({
                "code": "DOCUMENT_NOT_USABLE",
                "path": path,
                "document_id": document_id,
                "status": status if isinstance(status, str) else "invalid",
            })
            continue
        if not isinstance(content, str) or not content.strip():
            findings.append({"code": "DOCUMENT_CONTENT_EMPTY", "path": path, "document_id": document_id})
            continue
        if len(content) > 24_000 or total_chars + len(content) > 180_000:
            findings.append({"code": "DOCUMENT_CONTENT_LIMIT_EXCEEDED", "path": path, "document_id": document_id})
            continue
        actual_digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        declared_digest = document.get("content_sha256")
        if declared_digest is not None and declared_digest != actual_digest:
            findings.append({"code": "DOCUMENT_DIGEST_MISMATCH", "path": path, "document_id": document_id})
            continue
        total_chars += len(content)
        document_digest = actual_digest
        document_node_id = "document:" + hashlib.sha256(document_id.encode("utf-8")).hexdigest()[:24]
        if document_node_id in node_by_id:
            findings.append({"code": "DOCUMENT_NODE_ID_COLLISION", "path": path, "document_id": document_id})
            continue
        title = document.get("title")
        uri = document.get("uri")
        node = {
            "id": document_node_id,
            "kind": "source_document",
            "label": title.strip() if isinstance(title, str) and title.strip() else document_id,
            "attributes": {
                "document_id": document_id,
                "source_id": source_id if isinstance(source_id, str) else None,
                "status": status,
                "content_sha256": document_digest,
                "character_count": len(content),
            },
            "provenance": {
                "source_document_index": index,
                "project_id": project_id,
                "uri": uri if isinstance(uri, str) else None,
                "content_included": False,
            },
        }
        nodes.append(node)
        node_by_id[document_node_id] = node
        edges.append({
            "from": f"project:{project_id}",
            "to": document_node_id,
            "type": "has_indexed_source_document",
            "attributes": {
                "source_id": source_id if isinstance(source_id, str) else None,
                "document_status": status,
            },
            "evidence": f"source_documents[{index}].document_id",
            "epistemic_status": "indexed_reference_not_live_verified",
        })
        document_records.append({
            "document_id": document_id,
            "project_id": project_id,
            "source_id": source_id if isinstance(source_id, str) else None,
            "status": status,
            "content_sha256": document_digest,
            "character_count": len(content),
        })

        for term in _extract_terms(content):
            concept = term["term"]
            concept_id = f"concept:{concept}"
            evidence = {
                "kind": "source_document",
                "document_id": document_id,
                "project_id": project_id,
                "content_sha256": document_digest,
                "start": term["start"],
                "end": term["end"],
                "surface": term["surface"],
                "method": term["method"],
            }
            concept_projects[concept].add(project_id)
            concept_evidence[concept].append(evidence)
            concept_node = node_by_id.get(concept_id)
            if concept_node is None:
                concept_node = {
                    "id": concept_id,
                    "kind": "candidate_concept",
                    "label": concept,
                    "attributes": {"extraction": "lexical", "mention_count": 0, "project_count": 0, "owner_count": 0},
                    "provenance": {"mentions": []},
                }
                nodes.append(concept_node)
                node_by_id[concept_id] = concept_node
            concept_node["provenance"].setdefault("mentions", []).append(evidence)
            edges.append({
                "from": document_node_id,
                "to": concept_id,
                "type": "mentions_candidate_concept",
                "attributes": {
                    "extraction_method": term["method"],
                    "character_start": term["start"],
                    "character_end": term["end"],
                    "surface": term["surface"],
                },
                "evidence": f"documents[{document_id}].content:{term['start']}:{term['end']}",
                "epistemic_status": "candidate",
            })

    # Normalize concept statistics after merging manifest and document evidence.
    for concept, project_ids in concept_projects.items():
        node = node_by_id.get(f"concept:{concept}")
        if node is None:
            continue
        mentions = node.get("provenance", {}).get("mentions", [])
        node["attributes"]["mention_count"] = len(mentions)
        node["attributes"]["project_count"] = len(project_ids)
        node["attributes"]["owner_count"] = len({
            item.get("owner_id") or item.get("document_id")
            for item in mentions if isinstance(item, dict)
        })

    cross_project_candidates: list[dict[str, Any]] = []
    project_ids = sorted(projects)
    for index, left in enumerate(project_ids):
        for right in project_ids[index + 1:]:
            shared_concepts = sorted(
                concept for concept, owners in concept_projects.items()
                if left in owners and right in owners
            )
            shared_sources = sorted(project_source_ids[left] & project_source_ids[right])
            left_concepts = {concept for concept, owners in concept_projects.items() if left in owners}
            right_concepts = {concept for concept, owners in concept_projects.items() if right in owners}
            concept_union = left_concepts | right_concepts
            concept_score = len(left_concepts & right_concepts) / len(concept_union) if concept_union else 0.0
            if not shared_sources and (not shared_concepts or concept_score < threshold):
                continue
            relation = {
                "from": f"project:{left}",
                "to": f"project:{right}",
                "type": "cross_project_shared_evidence",
                "attributes": {
                    "shared_concepts": shared_concepts,
                    "shared_source_systems": shared_sources,
                    "concept_count": len(shared_concepts),
                    "concept_jaccard_score": round(concept_score, 6),
                    "threshold": threshold,
                    "source_system_count": len(shared_sources),
                    "interpretation": "shared_indexed_evidence_is_not_a_dependency_or_semantic_equivalence",
                },
                "evidence": json.dumps({
                    "concept_evidence": {
                        concept: [
                            item for item in concept_evidence.get(concept, [])
                            if item.get("project_id") in {left, right}
                        ]
                        for concept in shared_concepts
                    },
                    "shared_source_systems": shared_sources,
                }, ensure_ascii=False, sort_keys=True),
                "epistemic_status": "candidate",
            }
            edges.append(relation)
            cross_project_candidates.append(relation)

    # Stable edge identity is based only on the evidence-bearing edge payload.
    for edge in edges:
        identity = {key: edge.get(key) for key in ("from", "to", "type", "attributes", "evidence")}
        edge["edge_id"] = "edge:" + _canonical_digest(identity)[:24]

    node_ids = [node["id"] for node in nodes]
    duplicate_node_ids = sorted({value for value in node_ids if node_ids.count(value) > 1})
    graph_findings = []
    for edge_index, edge in enumerate(edges):
        if edge["from"] not in set(node_ids) or edge["to"] not in set(node_ids):
            graph_findings.append({
                "code": "DANGLING_GRAPH_EDGE",
                "edge_index": edge_index,
                "from": edge["from"],
                "to": edge["to"],
            })
    for node_id in duplicate_node_ids:
        graph_findings.append({"code": "DUPLICATE_NODE_ID", "node_id": node_id})

    model.update({
        "model_version": "2.0.0-experimental",
        "model_type": "ncm_cross_project_concept_graph",
        "documents": document_records,
        "source_documents_sha256": _canonical_digest([
            {key: item.get(key) for key in ("document_id", "project_id", "source_id", "status", "content_sha256")}
            for item in document_records
        ]),
        "cross_project": {
            "candidate_relations": len(cross_project_candidates),
            "shared_concept_count": sum(1 for owners in concept_projects.values() if len(owners) > 1),
            "projects_with_source_documents": len({item["project_id"] for item in document_records}),
            "source_documents_included": len(document_records),
            "source_documents_content_embedded": False,
        },
        "summary": {
            **model["summary"],
            "documents": len(document_records),
            "candidate_concepts": sum(1 for node in nodes if node.get("kind") == "candidate_concept"),
            "cross_project_relations": len(cross_project_candidates),
            "shared_concepts_across_projects": sum(1 for owners in concept_projects.values() if len(owners) > 1),
            "audit_findings": len(graph_findings) + len(model.get("manifest_findings", [])) + len(findings),
            "edges": len(edges),
        },
        "edges": edges,
        "nodes": nodes,
        "graph_findings": graph_findings,
        "source_document_findings": findings,
        "semantics": {
            **model["semantics"],
            "model_scope": "cross_project",
            "source_documents_used": bool(document_records),
            "source_document_text_embedded": False,
            "source_document_evidence_excerpts_embedded": True,
            "source_document_content_live_checked": False,
            "cross_project_relations_are_candidates": True,
            "semantic_understanding": False,
            "canonical_manifest_modified": False,
        },
    })
    return model


__all__ = ["build_cross_project_model"]
