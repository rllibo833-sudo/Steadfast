# Steadfast

**Keep coding agents aligned with the repository's actual state.** Steadfast is a local-first governance toolkit for scope control, repository contracts, evidence records, documentation-drift signals, release readiness, and implementation-budget reporting. It does not generate code, require an AI API, or send repository contents to a hosted service.

## Quick start

Requires Python 3.10+ and Git.

```bash
python -m pip install -e .
steadfast init
steadfast audit
steadfast scope-check
steadfast evidence-check
steadfast inventory
steadfast release-check
```

The equivalent module entry point is `python -m steadfast`. Initialization is non-destructive: existing policy, goal, and evidence files are never overwritten.

## Commands

- `steadfast init`: create missing policy, goal, and verification-evidence files.
- `steadfast audit [--base REF]`: check changed paths, required evidence, documentation drift, configured repository contracts, and implementation-line budget.
- `steadfast scope-check [--changed PATH ...]`: check explicit paths or the current Git working tree against the allowlist.
- `steadfast evidence-check [--evidence FILE]`: check that required evidence files exist and contain meaningful text. This is a presence check, not proof that a claim is true.
- `steadfast report [--format markdown|json|sarif]`: emit a human-readable report, JSON, or SARIF 2.1.0 for code-scanning integrations.
- `steadfast inventory`: produce a deterministic file inventory with SHA-256 digests, classification, file sizes, and budget usage.
- `steadfast release-check`: evaluate release prerequisites without publishing or modifying a release.

Exit codes: `0` no error findings, `1` one or more policy errors, `2` usage or runtime error. Documentation drift and a missing changelog are warnings rather than automatic failures.

## Policy

Edit `.steadfast/policy.json` to define:

- `allowed_paths`: paths agents may change.
- `documentation_paths`: paths that count as documentation updates.
- `required_evidence`: evidence files that must be present.
- `implementation_paths` and `ignored_paths`: inputs to the product-code line budget.
- `product_code_budget`: maximum counted implementation lines (starter default: 20,000).
- Optional `required_files` and `required_text`: simple repository contracts checked by audit and release readiness.

The line count includes nonblank lines that do not begin with `#`; it is a rough budget signal, not a language-aware complexity metric. The budget is a ceiling and planning signal. Increase implementation volume through useful capabilities, adapters, parsers, validators, reporting, and integration—not duplicated or generated filler.

## Structured evidence

For machine-readable evidence, use the `steadfast.evidence` module. Each record requires a claim, exact command, integer exit code, result, and ISO-8601 verification timestamp. Optional commit, environment, and limitation fields preserve context. The library validates records and writes files atomically. It deliberately does not invent successful outcomes or execute arbitrary commands on the user's behalf.

## GitHub Actions

Copy `.github/workflows/steadfast.yml` into a repository to run tests and governance checks on GitHub Actions. Before making it a required check, confirm the checkout depth and base-ref configuration support the comparisons you want, and tune the allowlist for your repository.

## Skills

`skills/` contains portable instruction packs for repo auditing, scope guarding, evidence checking, documentation synchronization, and release readiness. These are agent instructions, not technical enforcement; use them alongside the CLI.

## Principles and limitations

1. **Repository reality wins:** claims should be backed by implementation and evidence.
2. **No silent scope growth:** changed paths outside the allowlist are errors.
3. **Evidence before completion:** record exact commands, exit codes, and meaningful outcomes.
4. **Small core:** no server, database, model key, telemetry, or hosted dependency.
5. **Human-controlled policy:** Steadfast reports and blocks; it does not silently rewrite plans.

Static checks cannot prove semantic correctness, validate every test claim, or infer whether documentation is factually complete. SHA-256 inventory values identify file content but do not establish trust or authorship. Maintainers must define meaningful evidence and keep policy paths current.

## Development

```bash
python -m unittest discover -s tests -v
python -m steadfast --help
steadfast report --format sarif
```

MIT licensed. See `LICENSE`.
