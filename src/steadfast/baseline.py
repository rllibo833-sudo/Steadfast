from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .checks import run_audit

BASELINE_PATH = Path(".steadfast") / "audit-baseline.json"


def _fingerprint(finding: dict[str, Any]) -> str:
    return "|".join(str(finding.get(key, "")) for key in ("severity", "code", "path", "message"))


def create_baseline(repo: Path, base: str | None = None) -> dict[str, Any]:
    report = run_audit(repo, base)
    findings = sorted(_fingerprint(item) for item in report["findings"])
    return {
        "schema_version": 1,
        "created_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "repository": str(repo),
        "product_code_lines": report["product_code_lines"],
        "product_code_budget": report["product_code_budget"],
        "findings": findings,
    }


def write_baseline(repo: Path, base: str | None = None) -> Path:
    """Write an explicit baseline update; never called automatically by audit."""
    destination = repo / BASELINE_PATH
    destination.parent.mkdir(parents=True, exist_ok=True)
    snapshot = create_baseline(repo, base)
    temporary = destination.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(destination)
    return destination


def compare_baseline(repo: Path, base: str | None = None) -> dict[str, Any]:
    destination = repo / BASELINE_PATH
    try:
        saved = json.loads(destination.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {
            "ready": False,
            "findings": [{
                "severity": "warning", "code": "BASELINE_MISSING",
                "path": BASELINE_PATH.as_posix(),
                "message": "No baseline exists; create one explicitly with steadfast baseline-update.",
            }],
        }
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return {
            "ready": False,
            "findings": [{
                "severity": "error", "code": "BASELINE_INVALID",
                "path": BASELINE_PATH.as_posix(),
                "message": f"Baseline is unreadable or invalid JSON: {exc}",
            }],
        }
    if not isinstance(saved, dict) or saved.get("schema_version") != 1 or not isinstance(saved.get("findings"), list):
        return {
            "ready": False,
            "findings": [{
                "severity": "error", "code": "BASELINE_SCHEMA_INVALID",
                "path": BASELINE_PATH.as_posix(),
                "message": "Baseline schema is not supported.",
            }],
        }
    current = create_baseline(repo, base)
    old = set(str(item) for item in saved["findings"])
    new = set(current["findings"])
    added = sorted(new - old)
    resolved = sorted(old - new)
    findings = [{
        "severity": "error", "code": "NEW_BASELINE_FINDING",
        "path": value.split("|", 3)[2] if value.count("|") >= 3 else "",
        "message": f"New finding compared with baseline: {value}",
    } for value in added]
    return {
        "ready": not findings,
        "baseline": BASELINE_PATH.as_posix(),
        "added_findings": added,
        "resolved_findings": resolved,
        "previous_code_lines": saved.get("product_code_lines"),
        "current_code_lines": current["product_code_lines"],
        "findings": findings,
    }
