---
name: evidence-check
description: Ensure completion statements are backed by observed verification evidence.
---
# Evidence check
1. Identify acceptance criteria and relevant verification commands.
2. Run checks in the available environment; do not infer results from prior runs.
3. Capture the exact command, exit code, observed result, timestamp, commit and limitations.
4. Use the steadfast.evidence schema and validate records before saving.
5. Never claim a test, build, deployment or CI run succeeded unless its result was observed.
6. Run steadfast evidence-check and steadfast release-check before claiming completion.
