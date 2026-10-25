# Product goal

## Outcome
Provide a local-first, deterministic CLI for scope, evidence, and product-code budget checks.

## Non-goals
- Do not generate application code.
- Do not require hosted services or API credentials.
- Do not silently expand scope.

## Acceptance criteria
- [ ] Policy initialization preserves existing files.
- [ ] Scope checks flag paths outside the allowlist.
- [ ] Evidence checks detect missing proof.
- [ ] Product-code budget defaults to 20,000 lines.
- [ ] Unit tests pass in CI.
