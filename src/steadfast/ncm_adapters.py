from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Protocol


@dataclass(frozen=True)
class AdapterContext:
    """Read-only inputs made available to a project integration adapter."""

    project: Mapping[str, Any]
    source_documents: tuple[Mapping[str, Any], ...]
    ecosystem_manifest: Mapping[str, Any]


@dataclass
class AdapterResult:
    """Machine-readable, review-only output from one project adapter."""

    project_id: str
    adapter_id: str
    status: str
    capabilities: list[dict[str, Any]] = field(default_factory=list)
    outputs: list[dict[str, Any]] = field(default_factory=list)
    dependencies: list[dict[str, Any]] = field(default_factory=list)
    findings: list[dict[str, Any]] = field(default_factory=list)


class ProjectAdapter(Protocol):
    adapter_id: str

    def __call__(self, context: AdapterContext) -> AdapterResult: ...


class AdapterRegistry:
    """Explicit allowlist of trusted in-process adapters; nothing is imported dynamically."""

    def __init__(self) -> None:
        self._adapters: dict[str, ProjectAdapter] = {}

    def register(self, adapter: ProjectAdapter) -> None:
        adapter_id = getattr(adapter, "adapter_id", None)
        if not isinstance(adapter_id, str) or not adapter_id.strip():
            raise ValueError("Adapter must declare a non-empty adapter_id.")
        if adapter_id in self._adapters:
            raise ValueError(f"Adapter already registered: {adapter_id}")
        self._adapters[adapter_id] = adapter

    def get(self, adapter_id: str) -> ProjectAdapter | None:
        return self._adapters.get(adapter_id)


def run_project_adapters(
    manifest: Mapping[str, Any],
    source_documents: list[dict[str, Any]],
    registry: AdapterRegistry | None = None,
) -> dict[str, Any]:
    """Run only explicitly declared and registered adapters; unknown adapters fail closed."""
    active_registry = registry or AdapterRegistry()
    results: list[dict[str, Any]] = []
    projects = manifest.get("projects", [])
    if not isinstance(projects, list):
        projects = []

    for project in projects:
        if not isinstance(project, dict) or not isinstance(project.get("id"), str):
            continue
        project_id = project["id"]
        declaration = project.get("adapter")
        if not isinstance(declaration, dict) or not isinstance(declaration.get("id"), str):
            results.append({
                "project_id": project_id,
                "status": "not_configured",
                "adapter_id": None,
                "capabilities": [],
                "outputs": [],
                "dependencies": [],
                "findings": [{"code": "ADAPTER_NOT_DECLARED"}],
            })
            continue

        adapter_id = declaration["id"]
        adapter = active_registry.get(adapter_id)
        if adapter is None:
            results.append({
                "project_id": project_id,
                "status": "unavailable",
                "adapter_id": adapter_id,
                "capabilities": [],
                "outputs": [],
                "dependencies": [],
                "findings": [{"code": "ADAPTER_NOT_REGISTERED"}],
            })
            continue

        docs = tuple(
            item for item in source_documents
            if isinstance(item, dict) and item.get("project_id") == project_id
        )
        context = AdapterContext(project=project, source_documents=docs, ecosystem_manifest=manifest)
        try:
            result = adapter(context)
            if not isinstance(result, AdapterResult):
                raise TypeError("Adapter must return AdapterResult.")
            if result.project_id != project_id or result.adapter_id != adapter_id:
                raise ValueError("Adapter result identity does not match its declaration.")
            results.append({
                "project_id": result.project_id,
                "adapter_id": result.adapter_id,
                "status": result.status,
                "capabilities": result.capabilities,
                "outputs": result.outputs,
                "dependencies": result.dependencies,
                "findings": result.findings,
            })
        except Exception as exc:
            results.append({
                "project_id": project_id,
                "adapter_id": adapter_id,
                "status": "failed",
                "capabilities": [],
                "outputs": [],
                "dependencies": [],
                "findings": [{"code": "ADAPTER_EXECUTION_FAILED", "error_type": type(exc).__name__}],
            })

    return {
        "contract_version": "1.0.0",
        "status": "completed" if all(item["status"] in {"completed", "not_configured"} for item in results) else "partial",
        "summary": {
            "projects": len(results),
            "executed": sum(item["status"] == "completed" for item in results),
            "not_configured": sum(item["status"] == "not_configured" for item in results),
            "unavailable": sum(item["status"] == "unavailable" for item in results),
            "failed": sum(item["status"] == "failed" for item in results),
        },
        "results": results,
        "safety": {
            "dynamic_imports": False,
            "external_writes": False,
            "outputs_promoted": False,
        },
    }


__all__ = ["AdapterContext", "AdapterResult", "AdapterRegistry", "ProjectAdapter", "run_project_adapters"]
