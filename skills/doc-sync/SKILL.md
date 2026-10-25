---
name: doc-sync
description: Keep repository documentation aligned with actual code and test evidence.
---

# Documentation synchronization

1. Identify behavior changed in the current diff.
2. Find the existing documentation that describes that behavior.
3. Update only documents made stale by this change.
4. Verify feature claims against implementation and tests.
5. Remove or qualify claims that lack evidence.
6. Never invent test results, compatibility, benchmarks, or release status.
