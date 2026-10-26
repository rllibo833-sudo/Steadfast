# Changelog

## 0.2.0 — integrated governance core
- Added policy contract validation and optional required-file / required-text contracts.
- Added structured, timestamped verification evidence records with validation and atomic persistence.
- Added deterministic repository inventory with SHA-256 digests and implementation budget utilization.
- Added release-readiness checks that report blockers and warnings without publishing.
- Added SARIF 2.1.0 output for code-scanning integrations.
- Expanded regression coverage across contracts, evidence, inventory, release checks, and report conversion.
- CI status must be checked against the resulting GitHub Actions run; source commits alone do not prove a green pipeline.

## 0.1.0 — initial scaffold
- Local-first CLI for scope, evidence, and code budget checks.
- GitHub Actions workflow.
- Five portable agent skills.
- Standard-library tests.
