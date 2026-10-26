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
