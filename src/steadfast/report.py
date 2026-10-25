from __future__ import annotations
import json
from typing import Any

def render_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, ensure_ascii=False)

def render_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# Steadfast audit", "",
        f"- **Result:** {'PASS' if report['passed'] else 'FAIL'}",
        f"- **Product code:** {report['product_code_lines']:,} / {report['product_code_budget']:,} lines",
        f"- **Changed paths:** {len(report['changed_paths'])}",
        f"- **Errors:** {summary['errors']} · **Warnings:** {summary['warnings']} · **Info:** {summary['info']}",
        "", "## Findings", ""
    ]
    if not report["findings"]:
        lines.append("No findings.")
    for f in report["findings"]:
        lines.append(f"- **{f['severity'].upper()} `{f['code']}`** — `{f['path']}`: {f['message']}")
    lines += ["", "## Changed paths", ""]
    lines += [f"- `{p}`" for p in report["changed_paths"]] or ["- None detected."]
    lines.append("")
    return "\n".join(lines)
