# Product definition

Steadfast is a local-first repository governance CLI and portable agent toolkit. It inspects a repository against explicit policy, reports security and scope risks, checks verification evidence and documentation alignment, tracks implementation size, validates goal dependencies, compares audit baselines, runs reviewed verification pipelines, and exports machine-readable findings.

## Implemented capabilities

- **Repository audit:** allowlist enforcement, required evidence and file/text contracts, documentation-drift warnings, implementation budget checks, and combined findings.
- **Security review:** secret-pattern scanning with value redaction, risky dynamic execution/API warnings, and GitHub Actions trust-boundary checks.
- **Verification pipeline:** validated JSON dependency graphs, bounded parallel execution, dependency-failure handling, timeouts, output limits, and optional append-only JSONL execution history.
- **Governance data:** deterministic file inventory and SHA-256 digests, structured evidence records, explicit audit baselines, and goal-graph validation.
- **Integration:** CLI and module entry points, Markdown/JSON/SARIF reports, and GitHub Actions-compatible checks.

## Product boundaries

- Local-first: no hosted backend, AI API key, database, or telemetry is required.
- Policy-driven: repository owners configure allowed paths, evidence requirements, and implementation budgets.
- Review-oriented: static findings are signals, not proof of exploitability or semantic correctness. Pipeline manifests execute commands and must be reviewed before use.
- Non-destructive by default: audit commands report findings; baseline replacement is an explicit command.

## Maturity and scope

This is an actively developed implementation, not a claim of production certification. Remaining work includes deeper language-aware security analysis, more complete policy-schema validation, broader integration coverage, and stronger end-to-end release verification. The configured 20,000-line implementation budget is a ceiling/target constraint, not evidence that the codebase already contains 20,000 lines. Growth must come from distinct, integrated capabilities rather than duplicated code or documentation.

## Coding-agent integration and local console

Steadfast can generate policy guidance for Claude Code, Cursor, and Codex, while preserving existing integration files by default. The shared JSON hook checks repository-relative paths against the configured allowlist and blocks selected destructive shell command patterns. It does not execute commands and must be treated as defense-in-depth rather than a sandbox; agent hook schemas vary and should be reviewed against the installed version. The local Project Console provides read-only governance summaries and source previews.


## Evidence-gated work cycle

The cycle binds goal checklist items to repository-local evidence and observed pipeline/scope results. It records task transitions in an append-only JSONL event journal and stores the current task state separately. Completion is refused if verification fails, evidence is missing, or an evidence file changes after attachment. Evidence-file integrity does not establish semantic correctness; the evidence content still requires review.


### Console and agent integration

The Project Console surfaces the work-cycle state and recent journal events alongside audit, security, evidence and release signals. Agent hook responses carry a compact task context (task ID, goal ID and status), and generated skill instructions direct agents to inspect the cycle, attach per-criterion evidence, and run the configured verification gate before completion claims. The hook context is advisory; path and destructive-command findings remain the enforced decisions, and the local console does not mutate repository state.
