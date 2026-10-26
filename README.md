# Steadfast

**Keep coding agents aligned with the repository's actual state.** Steadfast is a local-first governance CLI for scope control, documentation-drift signals, evidence presence, and a configurable implementation-line budget. It does not generate code, require an AI API, or send repository contents to a hosted service.

## Quick start

Requires Python 3.10+ and Git.

```bash
python -m pip install -e .
steadfast init
steadfast audit
steadfast scope-check
steadfast evidence-check
```

The equivalent module entry point is `python -m steadfast`. Initialization is non-destructive: existing policy, goal, and evidence files are never overwritten.

## Commands

- `steadfast init`: create missing `.steadfast/policy.json`, `.steadfast/goal.md`, and `evidence/verification.md`.
- `steadfast audit [--base REF]`: report changed paths, scope violations, required-evidence gaps, implementation-line budget usage, and a documentation-drift warning when implementation changes without a docs change.
- `steadfast scope-check [--changed PATH ...]`: check explicit paths or the current Git working tree against `.steadfast/policy.json`.
- `steadfast evidence-check [--evidence FILE]`: check that required evidence files exist and contain meaningful text. This checks presence/size, not whether the claim is true.
- `steadfast report [--format markdown|json]`: print the complete audit report.

Exit codes: `0` no error findings, `1` one or more policy errors, `2` usage or runtime error. Documentation drift is a warning, not an automatic failure.

## Policy

Edit `.steadfast/policy.json` to define:

- `allowed_paths`: paths agents may change.
- `documentation_paths`: paths that count as documentation updates.
- `required_evidence`: evidence files that must be present.
- `implementation_paths` and `ignored_paths`: inputs to the product-code line budget.
- `product_code_budget`: maximum counted implementation lines (starter default: 20,000).

The line count includes nonblank lines that do not begin with `#`; it is a rough budget signal, not a language-aware complexity metric. Keep the allowlist narrow and review policy changes like code.

## GitHub Actions

Copy `.github/workflows/steadfast.yml` into a repository to run the tests and governance checks on GitHub Actions. Before making it a required check, confirm your checkout depth and base-ref configuration support the comparisons you want, and tune the allowlist for your repository.

## Skills

`skills/` contains portable instruction packs for repo auditing, scope guarding, evidence checking, documentation synchronization, and release readiness. These are agent instructions, not technical enforcement; use them alongside the CLI.

## Principles and limitations

1. **Repository reality wins:** claims should be backed by implementation and evidence.
2. **No silent scope growth:** changed paths outside the allowlist are errors.
3. **Evidence before completion:** record exact commands, exit codes, and meaningful outcomes.
4. **Small core:** no server, database, model key, telemetry, or hosted dependency.
5. **Human-controlled policy:** Steadfast reports and blocks; it does not silently rewrite plans.

Static checks cannot prove semantic correctness, validate every test claim, or infer whether documentation is factually complete. Maintainers must define meaningful evidence and keep policy paths current.

## Development

```bash
python -m unittest discover -s tests -v
python -m steadfast --help
steadfast audit --format json
```

MIT licensed. See `LICENSE`.
