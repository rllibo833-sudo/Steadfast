# Quick start

This guide gets Steadfast running in an existing Git repository.

## 1. Install

Use Python 3.10 or newer:

```bash
python -m pip install --upgrade steadfast-governance
```

## 2. Move into the repository

```bash
cd /path/to/your/repository
```

The target directory should be the Git repository you want to inspect—not the Steadfast source repository unless you are working on Steadfast itself.

## 3. Set up agent guidance

For Codex:

```bash
steadfast onboard --agent codex
```

Other supported targets are `claude`, `cursor`, and `all`. Review the files it creates before using them. Existing files are preserved by default.

## 4. Run a read-only check

```bash
steadfast verify
```

This produces a unified report from configured repository checks. A finding is a signal to review, not automatic proof of a bug. The command does not run the configured pipeline.

For a readable report:

```bash
steadfast report
```

## 5. Understand the local configuration

- `.steadfast/policy.json`: allowed paths, required evidence, documentation paths, and repository contracts.
- `.steadfast/goals/`: goal files and acceptance criteria.
- `.steadfast/pipeline.json`: commands for the separately invoked pipeline.

Review pipeline commands before running them because the manifest is executable configuration.

## Common next commands

- `steadfast discover` — machine-readable capability map.
- `steadfast audit` — repository governance checks.
- `steadfast docs-check` — CLI/documentation alignment.
- `steadfast security-check` — selected source and workflow risk signals.
- `steadfast --help` — complete top-level CLI help.

See [the command reference](COMMANDS.md) for the wider command list.
