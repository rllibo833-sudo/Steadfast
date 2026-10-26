---
name: release-readiness
description: Evaluate release readiness using policy and observed verification evidence.
---
# Release readiness
1. Run the configured verification pipeline and record the actual result.
2. Run steadfast audit, steadfast evidence-check, steadfast docs-check and steadfast release-check.
3. Review new baseline findings rather than automatically accepting them.
4. Confirm docs, version metadata, acceptance criteria and evidence refer to the same candidate.
5. Report blockers and missing evidence; never publish or tag without authorization.
