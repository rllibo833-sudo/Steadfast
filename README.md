# Steadfast

**Keep coding agents aligned with the repository's actual state.** Steadfast is a small, local-first governance CLI that checks documentation drift, scope expansion, and whether completion claims have evidence. It does not generate code or require an AI API.

## Quick start

Requires Python 3.10+ and Git.

```bash
python -m pip install -e .
steadfast init
steadfast audit
steadfast scope-check
steadfast evidence-check
```

`steadfast init` creates `.steadfast/policy.json` and `.steadfast/goal.md`. Review and commit those files. The policy is deliberately small: it defines allowed paths, documentation paths, required evidence, and the product-code line budget.

## Commands

- `steadfast audit [--base REF]`: checks repository state and reports likely documentation drift, generated/untracked files, and scope signals.
- `steadfast scope-check [--changed PATH ...]`: rejects changed paths outside configured allowlists. By default it checks Git's working-tree changes against the current policy.
- `steadfast evidence-check [--evidence FILE]`: checks required proof files and rejects empty evidence. It does not pretend that a passing test proves all product claims.
- `steadfast report [--format markdown|json]`: emits a machine-readable report.
- `steadfast init`: initializes policy files without overwriting existing ones.

Exit codes: `0` passed, `1` policy findings, `2` usage or runtime error.

## GitHub Actions

Copy `.github/workflows/steadfast.yml` into your repository. The workflow runs on pull requests and pushes, installs Steadfast, then runs its checks. Tune the allowlist in `.steadfast/policy.json` before enabling it as a required check.

## Skills

`skills/` contains portable instruction packs for common agent platforms. They are prompts and operating rules, not magical enforcement. Use them alongside the deterministic CLI checks.

## Principles

1. **Repository reality wins:** policy and docs must not claim features without implementation evidence.
2. **No silent scope growth:** changed paths must be explicitly allowed.
3. **Evidence before completion:** record the exact commands and results used to verify work.
4. **Small core:** no server, database, model key, telemetry, or hosted dependency.
5. **Human-controlled policy:** Steadfast reports and blocks; it does not silently rewrite project plans.

## Limitations

Static checks cannot fully infer semantic correctness or prove a feature works. A reviewer must define meaningful evidence and keep policy paths current. GitHub Actions consume runner minutes; use only the checks your project needs.

## Development

```bash
python -m unittest discover -s tests -v
python -m steadfast --help
```

MIT licensed. See `LICENSE`.
