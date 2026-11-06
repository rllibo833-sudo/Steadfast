from __future__ import annotations

from typing import Any


def build_concept_model(
    manifest: dict[str, Any],
    audit_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a deterministic, provenance-preserving concept graph from a universe manifest.

    This is an adapter/data projection, not an NCM reasoning engine. It does not
    infer hidden dependencies or rewrite source facts.
    """
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    source_ids: set[str] = set()
    project_ids: set[str] = set()
    node_ids: set[str] = set()

    for source in manifest.get("sources", []):
        if not isinstance(source, dict) or not isinstance(source.get("id"), str):
            continue
        source_id = source["id"]
        if source_id in source_ids:
            continue
        source_ids.add(source_id)
        node_ids.add(f"source:{source_id}")
        nodes.append({
            "id": f"source:{source_id}",
            "kind": "source_system",
            "label": source_id,
            "attributes": {
                "source_type": source.get("type"),
                "state": source.get("state"),
                "scope": source.get("scope"),
            },
            "provenance": {"manifest_field": f"sources[{source_id}]"},
        })

    for project in manifest.get("projects", []):
        if not isinstance(project, dict) or not isinstance(project.get("id"), str):
            continue
        project_id = project["id"]
        if project_id in project_ids:
            continue
        project_ids.add(project_id)
        project_node = f"project:{project_id}"
        node_ids.add(project_node)
        nodes.append({
            "id": project_node,
            "kind": "project",
            "label": project.get("name", project_id),
            "attributes": {
                "purpose": project.get("purpose"),
                "status": project.get("status", "unverified"),
            },
            "provenance": {"manifest_field": f"projects[{project_id}]"},
        })

        purpose = project.get("purpose")
        if isinstance(purpose, str) and purpose.strip():
            concept_id = f"concept:{project_id}:purpose"
            node_ids.add(concept_id)
            nodes.append({
                "id": concept_id,
                "kind": "declared_concept",
                "label": purpose.strip(),
                "attributes": {"extraction": "verbatim_project_purpose"},
                "provenance": {"manifest_field": f"projects[{project_id}].purpose"},
            })
            edges.append({
                "from": project_node,
                "to": concept_id,
                "type": "declares_purpose",
                "evidence": "universe.json",
                "epistemic_status": "source_declared",
            })

        for index, reference in enumerate(project.get("sources", [])):
            if not isinstance(reference, dict):
                continue
            source_id = reference.get("source_id")
            if source_id not in source_ids:
                continue
            edges.append({
                "from": project_node,
                "to": f"source:{source_id}",
                "type": "uses_source_system",
                "attributes": {
                    "uri": reference.get("uri"),
                    "role": reference.get("role"),
                    "source_status": reference.get("status"),
                },
                "evidence": f"projects[{project_id}].sources[{index}]",
                "epistemic_status": "indexed_reference_not_live_verified",
            })

    for index, relationship in enumerate(manifest.get("relationships", [])):
        if not isinstance(relationship, dict):
            continue
        source = relationship.get("from")
        target = relationship.get("to")
        source_node = f"project:{source}" if source in project_ids else f"system:{source}"
        target_node = f"project:{target}" if target in project_ids else f"system:{target}"
        if source_node.startswith("system:") and source_node not in node_ids:
            node_ids.add(source_node)
            nodes.append({
                "id": source_node,
                "kind": "external_system",
                "label": source,
                "attributes": {},
                "provenance": {"manifest_field": "relationships"},
            })
        if target_node.startswith("system:") and target_node not in node_ids:
            node_ids.add(target_node)
            nodes.append({
                "id": target_node,
                "kind": "external_system",
                "label": target,
                "attributes": {},
                "provenance": {"manifest_field": "relationships"},
            })
        edges.append({
            "from": source_node,
            "to": target_node,
            "type": relationship.get("type", "related_to"),
            "attributes": {"status": relationship.get("status", "unverified")},
            "evidence": f"relationships[{index}]",
            "epistemic_status": "manifest_asserted_not_independently_verified",
        })

    if audit_report:
        for index, finding in enumerate(audit_report.get("findings", [])):
            if not isinstance(finding, dict):
                continue
            finding_id = f"finding:{index}:{finding.get('code', 'unknown')}"
            nodes.append({
                "id": finding_id,
                "kind": "audit_finding",
                "label": finding.get("code", "Audit finding"),
                "attributes": {
                    "severity": finding.get("severity"),
                    "path": finding.get("path"),
                    "message": finding.get("message"),
                },
                "provenance": {"audit_report": audit_report.get("check", "unknown"), "finding_index": index},
            })

    return {
        "model_version": "1.0.0",
        "model_type": "ncm_concept_graph_projection",
        "source_manifest": {
            "universe_id": manifest.get("universe_id"),
            "manifest_version": manifest.get("manifest_version"),
        },
        "semantics": {
            "purpose": "Provide a stable graph input for a future NCM reasoning layer.",
            "inference_performed": False,
            "relationships_are_verified": False,
            "project_sources_are_live_checked": False,
            "source_text_is_preserved": True,
        },
        "summary": {
            "projects": sum(node["kind"] == "project" for node in nodes),
            "source_systems": sum(node["kind"] == "source_system" for node in nodes),
            "declared_concepts": sum(node["kind"] == "declared_concept" for node in nodes),
            "audit_findings": sum(node["kind"] == "audit_finding" for node in nodes),
            "edges": len(edges),
        },
        "nodes": nodes,
        "edges": edges,
    }
