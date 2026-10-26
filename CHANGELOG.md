# Changelog

## 0.4.0 — expanded governance and security core
- Added conservative local secret-pattern checks and workflow trust-boundary warnings.
- Integrated security findings into the main audit report and added a dedicated security-check command.
- Added goal dependency graphs, audit baseline regression checks, documentation synchronization, repository contracts, structured evidence, deterministic inventory, release readiness, and SARIF output.
- Expanded standard-library regression tests across the integrated modules.
- Hardened agent command guards to detect destructive commands chained with shell operators, with regression coverage for dangerous and harmless chains.
- Extended the guard to inspect nested shell launchers such as `bash -c`, `sh -c`, and `env`, while preserving harmless quoted text.
- Protected all `.steadfast/` policy, work-cycle, work-order, and evidence-ledger files from direct agent file-write tools to prevent easy governance-state tampering; runtime APIs remain responsible for legitimate state transitions.
- Expanded recursive forced-deletion detection to cover split (`rm -r -f`), reordered (`rm -f -r`), combined (`rm -fr`), and long-form flags.
- Release readiness now blocks on security-scanner errors and high-risk workflow trust-boundary findings instead of depending on an optional separately supplied audit report.
- Fixed the security scanner's source-suffix filter so `.env` and `.env.*` files are inspected rather than silently skipped.
- GitHub Actions status must be verified from a real workflow run; pushed commits are not themselves proof of CI success.

## 0.1.0 — initial scaffold
- Local-first CLI for scope, evidence, and code budget checks.
- GitHub Actions workflow.
- Five portable agent skills.
- Standard-library tests.
