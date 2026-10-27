---
name: ci-failure-autopsy
description: Diagnose a failing CI run from workflow logs, identify the first causal failure, reproduce it locally, and produce a minimal verified patch.
---
# CI failure autopsy

Use when a CI run is red, flaky, or failing only in automation. Deliver a causal diagnosis and, when authorized, a minimal fix—not a list of downstream errors.

## Procedure
1. Pin the exact commit, workflow, job, failed step, runner OS, runtime versions, run URL, and expected behavior. Fetch the failed step log; a red badge is not enough.
2. Read the log chronologically and identify the earliest causal error. Separate it from cascades such as missing artifacts caused by an earlier import failure. Quote only the smallest useful excerpt and redact secrets.
3. Classify the cause: source regression, assertion, dependency resolution, environment drift, permissions, external service/network, race/flakiness, or workflow wiring. State evidence for and against the leading hypothesis.
4. Compare the failing commit with the last known green commit. Inspect relevant diffs; do not blame the latest commit merely because it is latest.
5. Reproduce the failing command with matching versions and environment where possible. If exact reproduction is impossible, mark the hypothesis unconfirmed and add a focused regression check.
6. Fix the cause, not the symptom. Do not skip tests, weaken assertions, disable security checks, or use continue-on-error just to make CI green.
7. Re-run the narrow reproducer, relevant tests, and workflow validation. Report actual commands, exit codes, observed output, and remote run links only when observed.
8. Add a regression test or workflow assertion that would catch the original defect. Avoid tests that merely assert the implementation's current text.
9. Produce an incident note: first causal error, root-cause confidence, affected paths, minimal patch, verification, residual uncertainty, and whether the original failure is demonstrably fixed.

## Stop conditions
- Missing logs: obtain the exact job log rather than inventing a diagnosis.
- External outage or missing secret: identify the dependency and safe recheck; do not fabricate a source-code fix.
- Suspected secret exposure: redact the value and flag the exposure.
- No write authorization: provide a patch-ready diff without changing files.

## Acceptance criteria
- Root cause is separated from downstream noise and tied to a log excerpt or reproducible observation.
- Patch includes a regression guard and observed verification results.
- Confirmed facts, hypotheses, and unverified assumptions are labeled separately.
