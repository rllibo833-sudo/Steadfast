from __future__ import annotations

from pathlib import Path
from typing import Any

from .checks import run_audit
from .docsync import docs_sync_report
from .ecosystem import ecosystem_report
from .goals import goal_report
from .pipeline import run_pipeline
from .policy import load_policy
from .release import release_report
from .security import security_findings, workflow_findings
from .session_ledger import verify_session_ledger


def verification_report(repo: Path, *, run_configured_pipeline: bool = True) -> dict[str, Any]:
    """Run the unified Steadfast control-plane checks for one repository."""
    repo = repo.resolve()
    policy = load_policy(repo)
    components: dict[str, dict[str, Any]] = {}

    audit = run_audit(repo)
    components["audit"] = {"passed": bool(audit.get("passed")), "report": audit}

    security = security_findings(repo, policy) + workflow_findings(repo)
    components["security"] = {"passed": not any(item.get("severity") == "error" for item in security), "findings": security}

    goals = goal_report(repo, policy)
    components["goals"] = {"passed": not any(item.get("severity") == "error" for item in goals.get("findings", [])), "report": goals}

    docs = docs_sync_report(repo)
    components["documentation"] = {"passed": not any(item.get("severity") == "error" for item in docs.get("findings", [])), "report": docs}

    sessions = verify_session_ledger(repo)
    components["session_ledger"] = {"passed": bool(sessions.get("valid")), "report": sessions}

    release = release_report(repo, audit)
    components["release_readiness"] = {"passed": bool(release.get("ready")), "report": release}

    manifest = repo / ".steadfast" / "pipeline.json"
    if run_configured_pipeline and manifest.is_file():
        pipeline = run_pipeline(repo, Path('.steadfast/pipeline.json'))
        components["pipeline"] = {"passed": bool(pipeline.get("passed")), "report": pipeline}
    else:
        components["pipeline"] = {"passed": True, "skipped": True, "reason": "No configured .steadfast/pipeline.json" if not manifest.is_file() else "Pipeline execution disabled"}

    ecosystem = ecosystem_report(repo)
    components["ecosystem"] = {"passed": True, "informational": True, "report": ecosystem}

    blocking = [name for name, item in components.items() if not item.get("passed", False) and not item.get("informational", False)]
    return {
        "tool": "steadfast",
        "check": "unified-control-plane",
        "repository": str(repo),
        "passed": not blocking,
        "blocking_components": blocking,
        "components": components,
        "summary": {
            "checked_components": len(components),
            "passed_components": sum(1 for item in components.values() if item.get("passed", False)),
            "blocking_components": len(blocking),
        },
    }
