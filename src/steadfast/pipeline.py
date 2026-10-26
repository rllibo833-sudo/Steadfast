from __future__ import annotations

import json
import os
import re
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any


PIPELINE_VERSION = 1
_STEP_ID = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,63}$")
_ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
MAX_STEPS = 256
MAX_TIMEOUT = 3600
MAX_WORKERS = 16
MAX_CAPTURE = 64_000


class PipelineError(ValueError):
    """A pipeline manifest is invalid or cannot be safely executed."""


def _inside(root: Path, relative: str, field: str) -> Path:
    candidate = Path(relative)
    if candidate.is_absolute() or any(part == ".." for part in candidate.parts):
        raise PipelineError(f"{field} must be a repository-relative path")
    resolved = (root / candidate).resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise PipelineError(f"{field} resolves outside the repository") from exc
    return resolved


def load_pipeline(path: Path) -> dict[str, Any]:
    """Read and validate a versioned JSON pipeline manifest."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PipelineError(f"pipeline manifest not found: {path}") from exc
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PipelineError(f"pipeline manifest is unreadable or invalid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise PipelineError("pipeline manifest root must be a JSON object")
    if data.get("version") != PIPELINE_VERSION:
        raise PipelineError(f"pipeline version must be {PIPELINE_VERSION}")
    steps = data.get("steps")
    if not isinstance(steps, list) or not steps:
        raise PipelineError("pipeline steps must be a non-empty array")
    if len(steps) > MAX_STEPS:
        raise PipelineError(f"pipeline cannot contain more than {MAX_STEPS} steps")

    seen: set[str] = set()
    normalized: list[dict[str, Any]] = []
    for index, raw in enumerate(steps):
        label = f"steps[{index}]"
        if not isinstance(raw, dict):
            raise PipelineError(f"{label} must be an object")
        step_id = raw.get("id")
        if not isinstance(step_id, str) or not _STEP_ID.fullmatch(step_id):
            raise PipelineError(f"{label}.id must be 1-64 safe identifier characters")
        if step_id in seen:
            raise PipelineError(f"duplicate pipeline step id: {step_id}")
        seen.add(step_id)

        command = raw.get("command")
        if (not isinstance(command, list) or not command
                or any(not isinstance(arg, str) or not arg or "\x00" in arg for arg in command)):
            raise PipelineError(f"{label}.command must be a non-empty array of non-empty strings")
        dependencies = raw.get("depends_on", [])
        if (not isinstance(dependencies, list)
                or any(not isinstance(dep, str) or not dep for dep in dependencies)
                or len(set(dependencies)) != len(dependencies)):
            raise PipelineError(f"{label}.depends_on must be an array of unique step ids")
        timeout = raw.get("timeout", 300)
        if not isinstance(timeout, int) or isinstance(timeout, bool) or not 1 <= timeout <= MAX_TIMEOUT:
            raise PipelineError(f"{label}.timeout must be an integer from 1 to {MAX_TIMEOUT}")
        cwd = raw.get("cwd", ".")
        if not isinstance(cwd, str) or not cwd:
            raise PipelineError(f"{label}.cwd must be a repository-relative path")
        env = raw.get("env", {})
        if not isinstance(env, dict):
            raise PipelineError(f"{label}.env must be an object")
        for key, value in env.items():
            if (not isinstance(key, str) or not _ENV_NAME.fullmatch(key)
                    or not isinstance(value, str) or "\x00" in value):
                raise PipelineError(f"{label}.env must map valid environment names to strings")
        continue_on_error = raw.get("continue_on_error", False)
        if not isinstance(continue_on_error, bool):
            raise PipelineError(f"{label}.continue_on_error must be a boolean")
        normalized.append({
            "id": step_id, "command": command, "depends_on": dependencies,
            "timeout": timeout, "cwd": cwd, "env": env,
            "continue_on_error": continue_on_error,
        })

    ids = {step["id"] for step in normalized}
    for step in normalized:
        missing = sorted(set(step["depends_on"]) - ids)
        if missing:
            raise PipelineError(f"step {step['id']} depends on unknown step(s): {', '.join(missing)}")
        if step["id"] in step["depends_on"]:
            raise PipelineError(f"step {step['id']} cannot depend on itself")
    _assert_acyclic(normalized)
    return {"version": PIPELINE_VERSION, "steps": normalized}


def _assert_acyclic(steps: list[dict[str, Any]]) -> None:
    graph = {step["id"]: step["depends_on"] for step in steps}
    done: set[str] = set()
    visiting: set[str] = set()

    def visit(step_id: str) -> None:
        if step_id in visiting:
            raise PipelineError(f"pipeline dependency cycle includes step {step_id}")
        if step_id in done:
            return
        visiting.add(step_id)
        for dependency in graph[step_id]:
            visit(dependency)
        visiting.remove(step_id)
        done.add(step_id)

    for step in graph:
        visit(step)


def _bounded(text: str) -> str:
    if len(text) <= MAX_CAPTURE:
        return text
    return text[:MAX_CAPTURE] + f"\n...[truncated {len(text) - MAX_CAPTURE} characters]"


def _run_step(repo: Path, step: dict[str, Any]) -> dict[str, Any]:
    started = time.monotonic()
    cwd = _inside(repo, step["cwd"], f"step {step['id']}.cwd")
    if not cwd.is_dir():
        return {
            "id": step["id"], "status": "failed", "exit_code": None,
            "duration_seconds": 0.0, "command": step["command"],
            "stdout": "", "stderr": f"working directory does not exist: {step['cwd']}",
        }
    environment = os.environ.copy()
    environment.update(step["env"])
    try:
        proc = subprocess.run(
            step["command"], cwd=cwd, env=environment, shell=False,
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=step["timeout"], check=False,
        )
        stdout, stderr = proc.stdout, proc.stderr
        # Do not echo values supplied through manifest environment overrides.
        for value in step["env"].values():
            if len(value) >= 4:
                stdout = stdout.replace(value, "[REDACTED]")
                stderr = stderr.replace(value, "[REDACTED]")
        return {
            "id": step["id"], "status": "passed" if proc.returncode == 0 else "failed",
            "exit_code": proc.returncode, "duration_seconds": round(time.monotonic() - started, 3),
            "command": step["command"], "stdout": _bounded(stdout), "stderr": _bounded(stderr),
        }
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout or ""
        stderr = exc.stderr or ""
        if isinstance(stdout, bytes):
            stdout = stdout.decode("utf-8", errors="replace")
        if isinstance(stderr, bytes):
            stderr = stderr.decode("utf-8", errors="replace")
        return {
            "id": step["id"], "status": "timed_out", "exit_code": None,
            "duration_seconds": round(time.monotonic() - started, 3),
            "command": step["command"], "stdout": _bounded(stdout),
            "stderr": _bounded(stderr + f"\nstep exceeded {step['timeout']} second timeout"),
        }
    except OSError as exc:
        return {
            "id": step["id"], "status": "failed", "exit_code": None,
            "duration_seconds": round(time.monotonic() - started, 3),
            "command": step["command"], "stdout": "", "stderr": str(exc),
        }


def run_pipeline(
    repo: Path, manifest: Path | None = None, *, max_workers: int = 4,
) -> dict[str, Any]:
    """Execute a validated dependency graph; independent steps run concurrently."""
    root = repo.resolve()
    manifest_path = manifest or Path(".steadfast/pipeline.json")
    if manifest_path.is_absolute():
        try:
            manifest_path.resolve().relative_to(root)
        except ValueError as exc:
            raise PipelineError("pipeline manifest must be inside the repository") from exc
        manifest_path = manifest_path.resolve()
    else:
        manifest_path = _inside(root, manifest_path.as_posix(), "pipeline manifest")
    if not isinstance(max_workers, int) or isinstance(max_workers, bool) or not 1 <= max_workers <= MAX_WORKERS:
        raise PipelineError(f"max_workers must be from 1 to {MAX_WORKERS}")
    pipeline = load_pipeline(manifest_path)
    steps = pipeline["steps"]
    # Validate every working directory before starting any subprocess so a bad
    # later step cannot fail after earlier steps have already mutated the repo.
    for step in steps:
        _inside(root, step["cwd"], f"step {step['id']}.cwd")
    by_id = {step["id"]: step for step in steps}
    results: dict[str, dict[str, Any]] = {}
    pending = set(by_id)
    started = time.monotonic()

    with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="steadfast") as pool:
        while pending:
            ready = [
                step_id for step_id in by_id
                if step_id in pending and all(dep in results for dep in by_id[step_id]["depends_on"])
            ]
            if not ready:
                raise PipelineError("pipeline scheduler stalled despite validated dependency graph")
            runnable: list[str] = []
            for step_id in ready:
                step = by_id[step_id]
                blocked = [
                    dep for dep in step["depends_on"]
                    if results[dep]["status"] != "passed"
                    and not by_id[dep]["continue_on_error"]
                ]
                if blocked:
                    results[step_id] = {
                        "id": step_id, "status": "skipped", "exit_code": None,
                        "duration_seconds": 0.0, "command": step["command"],
                        "stdout": "", "stderr": "dependency did not pass: " + ", ".join(blocked),
                    }
                    pending.remove(step_id)
                else:
                    runnable.append(step_id)
            futures = {step_id: pool.submit(_run_step, root, by_id[step_id]) for step_id in runnable}
            for step_id in runnable:
                results[step_id] = futures[step_id].result()
                pending.remove(step_id)

    ordered = [results[step["id"]] for step in steps]
    counts = {status: sum(item["status"] == status for item in ordered)
              for status in ("passed", "failed", "timed_out", "skipped")}
    return {
        "tool": "steadfast", "pipeline_version": PIPELINE_VERSION,
        "manifest": manifest_path.relative_to(root).as_posix(),
        "passed": counts["failed"] == 0 and counts["timed_out"] == 0 and counts["skipped"] == 0,
        "duration_seconds": round(time.monotonic() - started, 3),
        "max_workers": max_workers, "summary": counts, "steps": ordered,
    }
