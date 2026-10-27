# Changelog

All notable changes to Steadfast are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and Steadfast uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Unreleased

### Added
- Added regression tests for security-scanner behavior, including secret redaction, risky API patterns, workflow shell interpolation, and action pinning.
- Added dashboard action tests for runtime token injection, missing-token rejection, cross-origin rejection, valid local actions, automation catalog access, and unknown actions.
- Added a repository pre-commit configuration for Ruff, common file hygiene checks, and optional type checking.
- Added a repository security policy covering vulnerability reporting, supported versions, responsible disclosure, and known limitations.

### Security
- Expanded automated regression coverage for security-scanner and dashboard-action protections.
- Documented that pattern-based scanning and heuristic analysis have limitations and are not substitutes for a full security review.

## 0.4.1 — MCP Registry publication
- Added the official MCP Registry ownership marker to the package README and aligned package/registry metadata for the 0.4.1 release.

## 0.4.0 — expanded governance and security core
- Added conservative local secret-pattern checks and workflow trust-boundary warnings.
- Integrated security findings into the main audit report and added a dedicated security-check command.
- Added goal dependency graphs, audit baseline regression checks, documentation synchronization, repository contracts, structured evidence, deterministic inventory, release readiness, and SARIF output.
- Expanded standard-library regression tests across the integrated modules.
- Hardened agent command guards to detect destructive commands chained with shell operators, with regression coverage for dangerous and harmless chains.
- Extended the guard to inspect nested shell launchers such as `bash -c`, `sh -c`, and `env`, while preserving harmless quoted text.
- Protected all `.steadfast/` policy, work-cycle, work-order, and evidence-ledger files from direct agent file-write tools to prevent easy governance-state tampering; runtime APIs remain responsible for legitimate state transitions.
- Expanded recursive forced-deletion detection to cover split (`rm -r -f`), reordered (`rm -f -r`), combined (`rm -fr`), and long-form flags.
- Extended destructive-command checks to privileged launchers (`doas`, `pkexec`), `find -delete`/`find -exec`, and `busybox rm` wrappers.
- Release readiness now blocks on security-scanner errors and high-risk workflow trust-boundary findings instead of depending on an optional separately supplied audit report.
- Release readiness also blocks broken CLI/module entrypoint contracts for packaged projects.
- Fixed the security scanner's source-suffix filter so `.env` and `.env.*` files are inspected rather than silently skipped.
- Pipeline commands now inherit a minimal runtime environment instead of every host/CI environment variable, reducing accidental exposure of runner secrets.
- Work-cycle evidence now rejects empty files and caps individual proof artifacts at 16 MiB before hashing.
- Policy initialization and loading reject a symlinked `.steadfast` directory or policy file to prevent writes/reads escaping the repository root.
- GitHub Actions status must be verified from a real workflow run; pushed commits are not themselves proof of CI success.

## 0.1.0 — initial scaffold
- Local-first CLI for scope, evidence, and code budget checks.
- GitHub Actions workflow.
- Five portable agent skills.
- Standard-library tests.
