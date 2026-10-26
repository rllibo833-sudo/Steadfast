# CLI command reference

Run `steadfast --help` or `steadfast COMMAND --help` for the options supported by the installed version.

## Setup and discovery

| Command | Purpose |
| --- | --- |
| `init` | Create missing starter policy, goal, and evidence files. |
| `onboard --agent TARGET` | Create governance foundation files and install selected local agent guidance/hooks. |
| `discover` | Emit a machine-readable capability map. |
| `mcp-server` | Serve read-only inspection tools over MCP stdio. |
| `integrate --agent TARGET` | Install agent-specific instructions and hook configuration. |
| `integration-status` | Report installed integration adapters. |
| `ecosystem [--strict]` | Inventory skill and MCP declarations and apply configured trust labels. |

Agent targets include `claude`, `cursor`, `codex`, and `all` where supported by the selected command.

## Verification and reporting

| Command | Purpose |
| --- | --- |
| `verify` | Run unified control-plane checks; does not execute the configured pipeline. |
| `audit [--base REF]` | Check changed paths, evidence, documentation drift, contracts, and implementation budget. |
| `report [--format markdown|json|sarif]` | Emit an audit report. |
| `scope-check [--changed PATH ...]` | Compare changed paths with the configured allowlist. |
| `agent-check --role code|media` | Check role-specific changed-path rules. |
| `evidence-check [--evidence FILE]` | Check required evidence presence and meaningful text. |
| `docs-check` | Check CLI declarations and package entrypoints against docs. |
| `code-truth` | Derive runtime CLI and package facts and flag stale CLI examples. |
| `security-check` | Scan selected source patterns and workflow trust boundaries. |
| `site-check SITE_DIR` | Audit a local static site without network access. |
| `impact-check [--base REF]` | Classify changes and suggest review gates and test/doc gaps. |
| `inventory` | Inventory files, digests, sizes, classifications, and budget use. |
| `release-check` | Evaluate release prerequisites without publishing. |

## Goals, findings, and evidence

| Command | Purpose |
| --- | --- |
| `goal-check` | Validate goal metadata, dependencies, cycles, acceptance criteria, and active-goal limits. |
| `plan [--goal ID]` | Build a dependency-aware execution queue or explain a goal. |
| `findings scan` | Refresh the finding ledger from configured live checks. |
| `findings list` | Filter findings by state, priority, or query. |
| `findings triage ID` | Record assignment, priority, due date, or accepted-risk decisions. |
| `findings resolve ID REASON` | Record an explicit resolution; live findings can reopen. |
| `findings history` | Inspect the tamper-evident finding event chain. |
| `findings metrics` | Summarize risk, accepted risks, and overdue items. |
| `baseline-update` | Explicitly save the current finding baseline. |
| `baseline-check` | Detect newly introduced findings relative to the saved baseline. |
| `evidence-bundle build` | Build a portable evidence bundle. |
| `evidence-bundle verify FILE` | Verify an evidence bundle. |

## Pipelines and work management

| Command | Purpose |
| --- | --- |
| `pipeline [--manifest FILE]` | Execute a reviewed JSON pipeline dependency graph. |
| `pipeline-history` | Inspect recent recorded pipeline executions. |
| `work-order issue` | Create a scoped work order. |
| `work-order list/show/verify/close` | Inspect and manage work orders. |
| `automation list` | List built-in automation actions. |
| `automation run NAME` | Execute a registered automation. |
| `automation history` | Inspect local automation history. |
| `serve` | Open the loopback-only read-only Project Console. |

Exact subcommands and options can change. The installed CLI's `--help` output is authoritative.

## Exit codes

- `0`: no error findings.
- `1`: policy errors or baseline regressions.
- `2`: usage or runtime error.

Some documentation drift and missing-changelog conditions are warnings rather than automatic failures. Read the command output for the distinction between errors, warnings, and informational findings.
