from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Protocol


@dataclass(frozen=True)
class AdapterContext:
    """Read-only inputs made available to a project integration adapter."""

    project: Mapping[str, Any]
    source_documents: tuple[Mapping[str, Any], ...]
    ecosystem_manifest: Mapping[str, Any]
    project_root: Path | None = None


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


class RepositorySmokeAdapter:
    """Run a fixed, reviewed read-only smoke command in a checked-out project."""

    def __init__(self, adapter_id: str, command: tuple[str, ...], capability: str, timeout: int = 180):
        self.adapter_id = adapter_id
        self.command = command
        self.capability = capability
        self.timeout = timeout

    def __call__(self, context: AdapterContext) -> AdapterResult:
        root = context.project_root
        if root is None or not root.is_dir():
            return AdapterResult(
                context.project["id"], self.adapter_id, "unavailable",
                findings=[{"code": "PROJECT_CHECKOUT_MISSING"}],
            )
        env = os.environ.copy()
        existing = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = os.pathsep.join(
            part for part in (str(root), str(root / "src"), existing) if part
        )
        try:
            completed = subprocess.run(
                list(self.command),
                cwd=root,
                env=env,
                text=True,
                capture_output=True,
                timeout=self.timeout,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return AdapterResult(
                context.project["id"], self.adapter_id, "failed",
                findings=[{"code": "ADAPTER_TIMEOUT", "timeout_seconds": self.timeout}],
            )
        except OSError as exc:
            return AdapterResult(
                context.project["id"], self.adapter_id, "failed",
                findings=[{"code": "ADAPTER_START_FAILED", "error_type": type(exc).__name__}],
            )
        ok = completed.returncode == 0
        return AdapterResult(
            project_id=context.project["id"],
            adapter_id=self.adapter_id,
            status="completed" if ok else "failed",
            capabilities=[{"id": self.capability, "verification": "smoke_test"}] if ok else [],
            outputs=[{
                "kind": "command_result",
                "exit_code": completed.returncode,
                "stdout_tail": completed.stdout[-2000:],
                "stderr_tail": completed.stderr[-2000:],
            }],
            findings=[] if ok else [{"code": "PROJECT_SMOKE_TEST_FAILED"}],
        )


class DocumentedOnlyAdapter:
    """Represent projects known only through documents without inventing runtime behavior."""

    def __init__(self, adapter_id: str = "documented-only"):
        self.adapter_id = adapter_id

    def __call__(self, context: AdapterContext) -> AdapterResult:
        return AdapterResult(
            project_id=context.project["id"],
            adapter_id=self.adapter_id,
            status="documented_only",
            outputs=[{
                "kind": "documented_project_state",
                "source_document_count": len(context.source_documents),
            }],
            findings=[{"code": "NO_EXECUTABLE_REPOSITORY_SOURCE"}],
        )


class ArchivedProjectAdapter:
    adapter_id = "ecos-archive"

    def __call__(self, context: AdapterContext) -> AdapterResult:
        root = context.project_root
        expected = ("README.md", "blender_scene.py", "trailer.py")
        present = [name for name in expected if root is not None and (root / name).is_file()]
        return AdapterResult(
            project_id=context.project["id"],
            adapter_id=self.adapter_id,
            status="archived",
            capabilities=[{"id": "ecos:archived-render-prototype", "verification": "repository_inventory"}],
            outputs=[{"kind": "archive_inventory", "expected_files": list(expected), "present_files": present}],
            findings=[{"code": "EXECUTION_DISABLED_ARCHIVED_PROJECT"}],
        )


def build_default_adapter_registry() -> AdapterRegistry:
    registry = AdapterRegistry()
    registry.register(RepositorySmokeAdapter(
        "pusingcuk-compiler",
        ("python", "-c", "from compiler.ir import from_source, validate; validate(from_source('', 'ncm-smoke')); import compiler.vm, compiler.self_hosted_frontend"),
        "pusingcuk:compiler-import-and-runtime",
    ))
    registry.register(RepositorySmokeAdapter(
        "mnemos-engine",
        ("python", "-c", "import mnemos.analysis, mnemos.device_mapper, mnemos.evolution, mnemos.forensics, mnemos.graph, mnemos.integrity, mnemos.store"),
        "mnemos:core-engine-import",
    ))
    registry.register(RepositorySmokeAdapter(
        "kawasan-masjid-site",
        ("npm", "run", "check"),
        "kawasan-masjid:production-site-validation",
        timeout=300,
    ))
    registry.register(ArchivedProjectAdapter())
    registry.register(DocumentedOnlyAdapter())
    registry.register(RepositorySmokeAdapter(
        "steadfast-governance",
        ("python", "-c", "import steadfast; import steadfast.ncm_runner; import steadfast.ncm_adapters"),
        "steadfast:ncm-orchestrator-import",
    ))
    return registry


def _project_roots_from_env(env: Mapping[str, str] | None) -> dict[str, Path]:
    source = env if env is not None else os.environ
    raw = source.get("NCM_PROJECT_ROOTS", "{}")
    try:
        values = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return {}
    if not isinstance(values, dict):
        return {}
    return {
        key: Path(value).resolve()
        for key, value in values.items()
        if isinstance(key, str) and isinstance(value, str) and value.strip()
    }


def run_project_adapters(
    manifest: Mapping[str, Any],
    source_documents: list[dict[str, Any]],
    registry: AdapterRegistry | None = None,
    *,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Run declared, registered adapters; unknown or absent adapters fail closed."""
    active_registry = registry or build_default_adapter_registry()
    roots = _project_roots_from_env(env)
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
                "project_id": project_id, "status": "not_configured", "adapter_id": None,
                "capabilities": [], "outputs": [], "dependencies": [],
                "findings": [{"code": "ADAPTER_NOT_DECLARED"}],
            })
            continue

        adapter_id = declaration["id"]
        adapter = active_registry.get(adapter_id)
        if adapter is None:
            results.append({
                "project_id": project_id, "status": "unavailable", "adapter_id": adapter_id,
                "capabilities": [], "outputs": [], "dependencies": [],
                "findings": [{"code": "ADAPTER_NOT_REGISTERED"}],
            })
            continue

        docs = tuple(
            item for item in source_documents
            if isinstance(item, dict) and item.get("project_id") == project_id
        )
        context = AdapterContext(
            project=project, source_documents=docs, ecosystem_manifest=manifest,
            project_root=roots.get(project_id),
        )
        try:
            result = adapter(context)
            if not isinstance(result, AdapterResult):
                raise TypeError("Adapter must return AdapterResult.")
            if result.project_id != project_id or result.adapter_id != adapter_id:
                raise ValueError("Adapter result identity does not match its declaration.")
            results.append({
                "project_id": result.project_id, "adapter_id": result.adapter_id,
                "status": result.status, "capabilities": result.capabilities,
                "outputs": result.outputs, "dependencies": result.dependencies,
                "findings": result.findings,
            })
        except Exception as exc:
            results.append({
                "project_id": project_id, "adapter_id": adapter_id, "status": "failed",
                "capabilities": [], "outputs": [], "dependencies": [],
                "findings": [{"code": "ADAPTER_EXECUTION_FAILED", "error_type": type(exc).__name__}],
            })

    terminal = {"completed", "archived", "documented_only", "not_configured"}
    summary = {
        "projects": len(results),
        "executed": sum(item["status"] == "completed" for item in results),
        "archived": sum(item["status"] == "archived" for item in results),
        "documented_only": sum(item["status"] == "documented_only" for item in results),
        "not_configured": sum(item["status"] == "not_configured" for item in results),
        "unavailable": sum(item["status"] == "unavailable" for item in results),
        "failed": sum(item["status"] == "failed" for item in results),
    }
    return {
        "contract_version": "1.0.0",
        "status": "completed" if all(item["status"] in terminal for item in results) else "partial",
        "summary": summary,
        "results": results,
        "safety": {
            "dynamic_imports": False, "external_writes": False,
            "outputs_promoted": False, "subprocess_commands_allowlisted": True,
        },
    }


__all__ = [
    "AdapterContext", "AdapterResult", "AdapterRegistry", "ProjectAdapter",
    "RepositorySmokeAdapter", "ArchivedProjectAdapter", "DocumentedOnlyAdapter",
    "build_default_adapter_registry", "run_project_adapters",
]
