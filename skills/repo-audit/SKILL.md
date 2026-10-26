---
name: repo-audit
description: Audit a repository against explicit policy and report reproducible findings.
---
# Repository audit
1. Read .steadfast/policy.json and identify the repository root.
2. Run steadfast audit and steadfast report --format json.
3. Group findings by severity and code; distinguish policy violations from heuristic warnings.
4. Never copy secret values into reports.
5. Do not change policy, baselines, or evidence merely to turn failures green.
6. Report commands, exit status, affected paths, and limitations.
