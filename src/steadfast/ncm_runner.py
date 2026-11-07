from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from .ncm_adapters import AdapterRegistry, derive_ecosystem_synthesis, run_project_adapters
from .ncm_backends import probe_backend_services
from .ncm_cross_project import build_cross_project_model
from .ncm_semantic import infer_semantic_candidates
from .ncm_sources import collect_source_documents
from .universe import load_universe_manifest


def run_ncm(
    repo: str | Path = ".",
    *,
    manifest_path: str = "ecosystem/universe.json",
    threshold: float = 0.2,
    allow_remote: bool = False,
    allow_source_content_remote: bool = False,
    env: Mapping[str, str] | None = None,
    adapter_registry: AdapterRegistry | None = None,
) -> dict[str, Any]:
    """Run the complete Next Concept Modelling workflow through one Python entry point."""
    root = Path(repo).resolve()
    path = Path(manifest_path)
    if not path.is_absolute():
        path = root / path
    manifest, manifest_findings = load_universe_manifest(path)
    if manifest is None:
        return {
            "model_type": "next_concept_model",
            "status": "failed",
            "manifest_findings": manifest_findings,
            "safety": {"manifest_modified": False, "external_systems_modified": False},
        }

    ingestion = collect_source_documents(manifest, env=env)
    documents = ingestion.get("documents", [])
    if not isinstance(documents, list):
        documents = []

    graph = build_cross_project_model(manifest, documents, threshold=threshold)
    adapter_layer = run_project_adapters(manifest, documents, adapter_registry, env=env)
    backend_layer = probe_backend_services(manifest)
    ecosystem_synthesis = derive_ecosystem_synthesis(adapter_layer)

    # Source text is sent to the semantic provider only with its separate consent flag.
    semantic_documents = documents if allow_source_content_remote else []
    semantic = infer_semantic_candidates(
        manifest,
        allow_remote=allow_remote,
        env=env,
        source_documents=semantic_documents,
        allow_source_content_remote=allow_source_content_remote,
        adapter_results=adapter_layer.get("results", []),
    )

    semantic_layer = {
        "status": semantic.get("status", "failed"),
        "concepts": semantic.get("concepts", []),
        "relations": semantic.get("relations", []),
        "possible_conflicts": semantic.get("possible_conflicts", []),
        "findings": semantic.get("findings", []),
        "error": semantic.get("error"),
        "reason": semantic.get("reason"),
        "summary": semantic.get("summary", {}),
        "source_manifest_sha256": semantic.get("source_manifest_sha256"),
        "source_documents_sha256": semantic.get("source_documents_sha256"),
        "adapter_results_sha256": semantic.get("adapter_results_sha256"),
        "safety": semantic.get("safety", {}),
    }

    # Merge validated semantic candidates into the same ecosystem graph.
    combined_graph = dict(graph)
    combined_graph["nodes"] = list(graph.get("nodes", []))
    combined_graph["edges"] = list(graph.get("edges", []))
    known_node_ids = {item.get("id") for item in combined_graph["nodes"] if isinstance(item, dict)}
    # Backend probes are read-only observations of deployed Edge Function routes.
    for backend in backend_layer.get("results", []):
        project_id = backend.get("project_id")
        service_id = backend.get("service_id")
        if not isinstance(project_id, str) or not isinstance(service_id, str):
            continue
        service_node_id = f"backend-service:{project_id}:{service_id}"
        combined_graph["nodes"].append({
            "id": service_node_id,
            "kind": "deployed_backend_service",
            "label": service_id,
            "attributes": {
                "status": backend.get("status"),
                "http_status": backend.get("http_status"),
                "auth_mode": backend.get("auth_mode"),
                "endpoint": backend.get("endpoint"),
            },
            "provenance": {"source": "read_only_supabase_edge_probe"},
            "epistemic_status": "runtime_probe_observed",
        })
        known_node_ids.add(service_node_id)
        if f"project:{project_id}" in known_node_ids:
            combined_graph["edges"].append({
                "from": f"project:{project_id}",
                "to": service_node_id,
                "type": "exposes_deployed_backend_service",
                "attributes": {"probe_status": backend.get("status")},
                "evidence": "backend_layer.results",
                "epistemic_status": "runtime_probe_observed",
            })
    for concept in semantic_layer["concepts"]:
        concept_id = concept.get("id")
        if not isinstance(concept_id, str) or concept_id in known_node_ids:
            continue
        combined_graph["nodes"].append({
            "id": concept_id,
            "kind": "semantic_candidate_concept",
            "label": concept.get("name", concept_id),
            "attributes": {"definition": concept.get("definition", "")},
            "provenance": {"evidence": concept.get("evidence", [])},
            "epistemic_status": "candidate",
        })
        known_node_ids.add(concept_id)
    accepted_semantic_relations = 0
    for relation_index, relation in enumerate(semantic_layer["relations"]):
        source_id, target_id = relation.get("from"), relation.get("to")
        if source_id not in known_node_ids or target_id not in known_node_ids:
            semantic_layer["findings"].append({
                "code": "SEMANTIC_RELATION_ENDPOINT_NOT_IN_GRAPH",
                "item": relation_index,
            })
            continue
        edge = {
            "from": source_id,
            "to": target_id,
            "type": relation["type"],
            "attributes": {
                "rationale": relation["rationale"],
                "confidence": relation["confidence"],
                "semantic_model_candidate": True,
            },
            "evidence": json.dumps(relation["evidence"], ensure_ascii=False, sort_keys=True),
            "epistemic_status": "candidate",
        }
        identity = json.dumps(edge, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        edge["edge_id"] = "edge:semantic:" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]
        combined_graph["edges"].append(edge)
        accepted_semantic_relations += 1
    # Add deterministic emergent concepts and observed orchestration edges.
    for concept in ecosystem_synthesis.get("emergent_concepts", []):
        concept_id = concept.get("id")
        if not isinstance(concept_id, str) or concept_id in known_node_ids:
            continue
        combined_graph["nodes"].append({
            "id": concept_id,
            "kind": "emergent_ecosystem_concept",
            "label": concept.get("name", concept_id),
            "attributes": {
                "definition": concept.get("definition", ""),
                "derivation": concept.get("derivation"),
            },
            "provenance": {"evidence": concept.get("evidence", [])},
            "epistemic_status": "candidate",
        })
        known_node_ids.add(concept_id)
    for relation in ecosystem_synthesis.get("orchestration_relations", []):
        combined_graph["edges"].append({
            "from": relation["from"],
            "to": relation["to"],
            "type": relation["type"],
            "attributes": {
                "rationale": relation["rationale"],
                "confidence": relation["confidence"],
                "derivation": "deterministic_adapter_synthesis",
            },
            "evidence": json.dumps(relation["evidence"], ensure_ascii=False, sort_keys=True),
            "epistemic_status": "observed_orchestration_candidate",
        })
    # Adapter outputs become first-class nodes and edges in the same ecosystem graph.
    adapter_capabilities = 0
    adapter_outputs = 0
    for adapter_result in adapter_layer.get("results", []):
        project_id = adapter_result.get("project_id")
        if not isinstance(project_id, str):
            continue
        project_node_id = f"project:{project_id}"
        for capability in adapter_result.get("capabilities", []):
            if not isinstance(capability, dict):
                continue
            capability_key = capability.get("id")
            if not isinstance(capability_key, str) or not capability_key:
                continue
            capability_node_id = f"adapter-capability:{project_id}:{capability_key}"
            if capability_node_id not in known_node_ids:
                combined_graph["nodes"].append({
                    "id": capability_node_id,
                    "kind": "verified_project_capability",
                    "label": capability.get("name", capability_key),
                    "attributes": {key: value for key, value in capability.items() if key not in {"id", "name"}},
                    "provenance": {"project_id": project_id, "adapter_id": adapter_result.get("adapter_id")},
                    "epistemic_status": "adapter_smoke_verified",
                })
                known_node_ids.add(capability_node_id)
                adapter_capabilities += 1
                combined_graph["edges"].append({
                    "from": project_node_id,
                    "to": capability_node_id,
                    "type": "exposes_verified_capability",
                    "attributes": {"adapter_id": adapter_result.get("adapter_id")},
                    "evidence": "adapter_layer.results.capabilities",
                    "epistemic_status": "adapter_smoke_verified",
                })
        for output_index, output in enumerate(adapter_result.get("outputs", [])):
            if not isinstance(output, dict):
                continue
            output_node_id = f"adapter-output:{project_id}:{adapter_result.get('adapter_id')}:{output_index}"
            combined_graph["nodes"].append({
                "id": output_node_id,
                "kind": "project_adapter_output",
                "label": f"{project_id} adapter output {output_index + 1}",
                "attributes": output,
                "provenance": {"project_id": project_id, "adapter_id": adapter_result.get("adapter_id")},
                "epistemic_status": "observed_adapter_output",
            })
            known_node_ids.add(output_node_id)
            adapter_outputs += 1
            combined_graph["edges"].append({
                "from": project_node_id,
                "to": output_node_id,
                "type": "produced_adapter_output",
                "attributes": {"adapter_status": adapter_result.get("status")},
                "evidence": "adapter_layer.results.outputs",
                "epistemic_status": "observed_adapter_output",
            })
            if output.get("kind") == "cross_project_integration":
                producer = output.get("producer_project")
                consumer = output.get("consumer_project")
                if producer and consumer and f"project:{producer}" in known_node_ids and f"project:{consumer}" in known_node_ids:
                    combined_graph["edges"].extend([
                        {
                            "from": f"project:{producer}", "to": output_node_id,
                            "type": "provided_cross_project_payload",
                            "attributes": {"contract": output.get("contract")},
                            "evidence": "adapter_layer.results.outputs",
                            "epistemic_status": "end_to_end_contract_verified",
                        },
                        {
                            "from": output_node_id, "to": f"project:{consumer}",
                            "type": "consumed_cross_project_payload",
                            "attributes": {"contract": output.get("contract")},
                            "evidence": "adapter_layer.results.outputs",
                            "epistemic_status": "end_to_end_contract_verified",
                        },
                    ])
    combined_graph["summary"] = {
        **combined_graph.get("summary", {}),
        "adapter_capabilities": adapter_capabilities,
        "adapter_outputs": adapter_outputs,
        "nodes": len(combined_graph["nodes"]),
        "edges": len(combined_graph["edges"]),
    }
    combined_graph["semantic_review_queue"] = semantic_layer["possible_conflicts"]
    combined_graph["summary"] = {
        **combined_graph.get("summary", {}),
        "candidate_concepts": graph.get("summary", {}).get("candidate_concepts", 0)
        + len(semantic_layer["concepts"]) + len(ecosystem_synthesis["emergent_concepts"]),
        "cross_project_relations": graph.get("summary", {}).get("cross_project_relations", 0)
        + accepted_semantic_relations,
        "semantic_conflicts_for_review": len(semantic_layer["possible_conflicts"]),
        "emergent_concepts": ecosystem_synthesis["summary"]["emergent_concepts"],
        "orchestration_relations": ecosystem_synthesis["summary"]["orchestration_relations"],
        "nodes": len(combined_graph["nodes"]),
        "edges": len(combined_graph["edges"]),
    }
    has_findings = bool(manifest_findings or graph.get("graph_findings") or graph.get("manifest_findings"))
    has_partial_sources = bool(ingestion.get("failures"))
    has_adapter_issues = adapter_layer.get("status") != "completed"
    semantic_failed = semantic_layer["status"] in {"failed", "error"}
    has_semantic_rejections = bool(semantic_layer.get("findings"))
    has_backend_failures = backend_layer.get("summary", {}).get("failed", 0) > 0
    has_inactive_backends = backend_layer.get("summary", {}).get("project_inactive", 0) > 0
    model_status = "partial" if (has_findings or has_partial_sources or has_adapter_issues or semantic_failed or has_semantic_rejections or has_backend_failures or has_inactive_backends) else "completed"
    return {
        "model_type": "next_concept_model",
        "model_version": "1.0.0",
        "status": model_status,
        "manifest_findings": manifest_findings,
        "source_ingestion": {
            "summary": ingestion.get("summary", {}),
            "failures": ingestion.get("failures", []),
            "safety": ingestion.get("safety", {}),
        },
        "ecosystem_graph": combined_graph,
        "semantic_layer": semantic_layer,
        "adapter_layer": adapter_layer,
        "backend_layer": backend_layer,
        "ecosystem_synthesis": ecosystem_synthesis,
        "summary": {
            "projects": graph.get("summary", {}).get("projects", 0),
            "source_documents": len(graph.get("documents", [])),
            "candidate_concepts": graph.get("summary", {}).get("candidate_concepts", 0) + len(semantic_layer["concepts"]) + len(ecosystem_synthesis["emergent_concepts"]),
            "cross_project_relations": graph.get("summary", {}).get("cross_project_relations", 0) + len(semantic_layer["relations"]),
            "semantic_status": semantic_layer["status"],
            "source_failures": len(ingestion.get("failures", [])),
            "semantic_rejected_items": len(semantic_layer["findings"]),
            "graph_findings": len(graph.get("graph_findings", [])) + len(graph.get("manifest_findings", [])),
            "adapters_executed": adapter_layer["summary"]["executed"],
            "adapters_not_configured": adapter_layer["summary"]["not_configured"],
            "adapters_unavailable": adapter_layer["summary"]["unavailable"],
            "adapter_failures": adapter_layer["summary"]["failed"],
            "adapter_archived": adapter_layer["summary"].get("archived", 0),
            "adapter_documented_only": adapter_layer["summary"].get("documented_only", 0),
            "adapter_capabilities": adapter_capabilities,
            "adapter_outputs": adapter_outputs,
            "emergent_concepts": ecosystem_synthesis["summary"]["emergent_concepts"],
            "orchestration_relations": ecosystem_synthesis["summary"]["orchestration_relations"],
            "backend_services": backend_layer.get("summary", {}).get("services", 0),
            "backend_services_ready": backend_layer.get("summary", {}).get("ready", 0),
            "backend_services_auth_required": backend_layer.get("summary", {}).get("reachable_auth_required", 0),
            "backend_service_failures": backend_layer.get("summary", {}).get("failed", 0),
            "backend_services_project_inactive": backend_layer.get("summary", {}).get("project_inactive", 0),
        },
        "safety": {
            "manifest_modified": False,
            "external_systems_modified": False,
            "source_documents_sent_to_model": bool(semantic_documents and allow_remote and allow_source_content_remote),
            "semantic_candidates_promoted": False,
        },
    }


def render_ncm(result: dict[str, Any]) -> str:
    return json.dumps(result, indent=2, ensure_ascii=False) + "\n"


__all__ = ["run_ncm", "render_ncm"]
