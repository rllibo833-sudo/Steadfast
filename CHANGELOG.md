# Changelog

## 0.4.0 — expanded governance and security core
- Added conservative local secret-pattern checks and workflow trust-boundary warnings.
- Integrated security findings into the main audit report and added a dedicated security-check command.
- Added goal dependency graphs, audit baseline regression checks, documentation synchronization, repository contracts, structured evidence, deterministic inventory, release readiness, and SARIF output.
- Expanded standard-library regression tests across the integrated modules.
- Hardened agent command guards to detect destructive commands chained with shell operators, with regression coverage for dangerous and harmless chains.
- Extended the guard to inspect nested shell launchers such as `bash -c`, `sh -c`, and `env`, while preserving harmless quoted text.
- GitHub Actions status must be verified from a real workflow run; pushed commits are not themselves proof of CI success.

## 0.1.0 — initial scaffold
- Local-first CLI for scope, evidence, and code budget checks.
- GitHub Actions workflow.
- Five portable agent skills.
- Standard-library tests.
