---
id: policy-consistency
title: Keep initialized and repository policy consistent
status: ready
depends_on: []
---

# Keep initialized and repository policy consistent

## Outcome
New repositories initialized by Steadfast receive the same default governance rules that the Steadfast repository itself documents and tests.

## Acceptance criteria
- [ ] `DEFAULT_POLICY` matches `.steadfast/policy.json` exactly.
- [ ] Policy loading rejects a non-object JSON root.
- [ ] Policy loading rejects booleans as integer code budgets.
- [ ] Policy regression tests pass in CI.

## Verification
Run `python -m unittest discover -s tests -v` from an installed development checkout.
