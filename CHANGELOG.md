# Changelog

## 0.3.0 — integrated governance workflows
- Added dependency-aware goal graph checks for missing dependencies, cycles, duplicate IDs, active-goal limits, and acceptance criteria.
- Added explicit audit baselines and regression comparison; audits never rewrite baselines implicitly.
- Added documentation synchronization checks for CLI commands and package entrypoints.
- Added optional repository contract validation.
- Added structured verification evidence, deterministic inventory, release readiness, and SARIF 2.1.0 output.
- Expanded standard-library regression coverage for the integrated governance modules.
- GitHub Actions status still needs confirmation from an actual workflow run; source commits alone are not proof of a green pipeline.

## 0.1.0 — initial scaffold
- Local-first CLI for scope, evidence, and code budget checks.
- GitHub Actions workflow.
- Five portable agent skills.
- Standard-library tests.
