from __future__ import annotations

from typing import Any

SARIF_VERSION = "2.1.0"
TOOL_NAME = "Steadfast"


def to_sarif(report: dict[str, Any]) -> dict[str, Any]:
    """Convert a Steadfast report into SARIF 2.1.0 for code-scanning systems."""
    findings = report.get("findings", [])
    rules: dict[str, dict[str, str]] = {}
    results = []
    for finding in findings:
        code = str(finding.get("code", "UNKNOWN"))
        severity = finding.get("severity", "warning")
        level = "error" if severity == "error" else "note" if severity == "info" else "warning"
        rules.setdefault(code, {
            "id": code,
            "name": code.replace("_", " ").title(),
            "shortDescription": {"text": str(finding.get("message", code))},
        })
        location: dict[str, Any] = {}
        path = finding.get("path")
        if path:
            location = {"physicalLocation": {
                "artifactLocation": {"uri": str(path).replace("\\", "/")}
            }}
        results.append({
            "ruleId": code,
            "level": level,
            "message": {"text": str(finding.get("message", code))},
            **({"locations": [location]} if location else {}),
        })
    return {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": SARIF_VERSION,
        "runs": [{
            "tool": {"driver": {
                "name": TOOL_NAME,
                "informationUri": "https://github.com/rllibo833-sudo/Steadfast",
                "rules": list(rules.values()),
            }},
            "results": results,
        }],
    }


def render_sarif(report: dict[str, Any]) -> str:
    import json
    return json.dumps(to_sarif(report), indent=2, ensure_ascii=False)
