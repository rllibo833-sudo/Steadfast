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
| `universe-check [--manifest PATH]` | Validate the cross-platform ecosystem manifest, IDs, source references, and relationship endpoints. Remote references are syntax-checked only. |
| `universe-model [--manifest PATH] [--include-audit]` | Export a provenance-preserving graph of declared facts. No inference or source mutation. |
| `universe-infer [--manifest PATH] [--threshold SCORE]` | Run the original purpose-text lexical candidate prototype. |
| `universe-analyze [--manifest PATH] [--threshold SCORE] [--output PATH]` | Build a multi-field concept graph and optionally save a model artifact with a SHA-256 digest. |
| `universe-review --model PATH --ledger PATH` | Validate human decisions against the exact model digest and candidate edge IDs; never promotes candidates to verified. |

Agent targets include `claude`, `cursor`, `codex`, and `all` where supported by the selected command.

## Cross-platform ecosystem index

The default manifest path is `ecosystem/universe.json`. The validator checks JSON structure, required top-level fields, duplicate IDs, unknown source IDs, and relationship endpoints. `local://` references are checked relative to the index root. HTTP(S) references are not fetched, and no project source is changed. Output is JSON and includes a safety summary.

Example:

```bash
steadfast universe-check
```

## Experimental NCM graph projection

Run `steadfast universe-model` to emit a deterministic JSON graph from the ecosystem manifest. Add `--include-audit` to include validation findings as graph nodes. The adapter preserves declared facts and provenance. `universe-infer` is a separate experimental symbolic baseline: it extracts tokens and adjacent phrases from each declared project purpose, records exact character offsets, builds candidate-concept nodes, scores shared project terms with Jaccard similarity, and reconciles candidate project pairs against manifest relationship endpoints. A matching declared pair is not proof of correctness; a missing pair is not a contradiction. All inferred items remain `candidate` and require human review. `universe-analyze` also extracts from project names, purposes, source-reference roles/titles/evidence, source scopes, consumer roles, and inventory notes. It emits source-system and consumer nodes, preserves field-level spans, flags unresolved source IDs and dangling graph edges, and keeps manifest-declared source links epistemically separate from inferred links. No source is modified and no remote source is queried. Use `universe-analyze --output build/ncm-model.json` to save an artifact. The command prints its SHA-256 digest; a separate review ledger must bind to that digest. `universe-review --model build/ncm-model.json --ledger reviews/session.json` validates reviewer identity, timestamp, edge IDs, rationale, and evidence references. Review decisions are sidecar records and never change the manifest or promote candidate edges to verified.

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


## Live ecosystem source checks

- `steadfast universe-sources` performs read-only metadata probes for Notion, Supabase, Cloudflare Workers, and a local JBF/Termux directory.
- Configure `NOTION_API_TOKEN`, `SUPABASE_ACCESS_TOKEN`, `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`, and optionally `JBF_ROOT` as environment variables. Use least-privilege read-only tokens. Secrets are never written to reports.
- A missing credential is reported as `not_configured`; an inactive Supabase project is not treated as unreachable.
- `steadfast universe-semantic --allow-remote` sends project descriptions and declared relationships to an explicitly configured OpenAI-compatible chat-completions endpoint. Set `NCM_API_KEY`, `NCM_MODEL`, and optionally `NCM_BASE_URL`. Without `--allow-remote`, no network request is made.
- Semantic concepts, relations, and possible conflicts remain candidates. Evidence quotes must match the exact manifest fields; human review is still required.
- Neither command modifies the manifest, remote services, or device files. The Termux probe checks metadata paths only; it does not execute commands or inspect private files.
