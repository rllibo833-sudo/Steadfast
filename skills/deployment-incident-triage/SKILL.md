---
name: deployment-incident-triage
description: Diagnose failed or unhealthy deployments using release diffs, deploy events, application logs, health checks, and metrics; isolate the first causal failure, decide rollback versus forward fix, and verify recovery.
---

# Deployment Incident Triage

Use when a deploy fails, a service becomes unhealthy after release, readiness checks fail, error rates spike, or a rollout stalls.

## Procedure

1. **Establish impact and timeline**: identify service/environment, deploy ID and timestamp, last known healthy version, affected endpoints, user-visible symptoms, and current health. Separate observed facts from hypotheses.
2. **Find the first causal signal**: inspect deploy events, build/runtime logs, startup errors, readiness/liveness probes, dependency failures, and error/latency metrics around the change. Prefer the earliest causal error over downstream noise.
3. **Compare versions**: inspect the deployed diff and configuration changes against the last healthy revision. Check migrations, secrets/config bindings, dependency changes, resource limits, and platform/runtime compatibility.
4. **Contain safely**: recommend rollback when the regression is release-linked and rollback is compatible with current data/schema state. Check migration reversibility and side effects first. Do not execute production rollback, change traffic, or alter secrets without explicit authorization.
5. **Prove the fix**: reproduce locally or in staging where feasible; implement the smallest root-cause fix; add a regression test or health assertion. Avoid speculative changes unrelated to evidence.
6. **Verify recovery**: confirm the intended version is serving, readiness and critical endpoints pass, error/latency metrics recover, and logs stop showing the causal failure. State the observation window and any remaining uncertainty.

## Required output

Give impact, timeline, first causal evidence, root cause versus unresolved hypotheses, containment decision, exact fix, verification evidence, and follow-up prevention. Never claim recovery based only on a successful build or deployment status.
