# Steadfast

**Repository checks and guardrails for coding agents.**

Steadfast is a local-first CLI that helps developers and AI agents inspect repository health, enforce change scope, verify evidence, and spot documentation drift. It does not generate code, require an AI API key, or send repository contents to a Steadfast-hosted service.

## Quick start

Requires Python 3.10+ and Git.

```bash
python -m pip install --upgrade steadfast-governance
cd /path/to/your/repository
steadfast onboard --agent codex
steadfast verify
```

Replace `codex` with `claude`, `cursor`, or `all` to configure another supported agent. Review generated files before trusting a repository. Existing files are preserved by default.

For the latest unreleased source, install from Git instead:

```bash
python -m pip install --upgrade "git+https://github.com/rllibo833-sudo/Steadfast.git"
```

## The commands most people need

| Command | Purpose |
| --- | --- |
| `steadfast onboard` | Set up repository guidance and selected agent integration. |
| `steadfast verify` | Run the unified, read-only governance checks. |
| `steadfast report` | Generate a human-readable audit report. |
| `steadfast audit` | Check changed files, evidence, contracts, and documentation drift. |
| `steadfast discover` | Print a machine-readable capability map for tools and agents. |
| `steadfast mcp-server` | Start the read-only MCP server for compatible agents. |

See the [quick-start guide](docs/QUICKSTART.md) for a short walkthrough and the [command reference](docs/COMMANDS.md) for the full CLI list. For a copy-ready pull-request workflow and an adoption checklist, see [Adopt in GitHub Actions](docs/ADOPT_IN_GITHUB_ACTIONS.md).

## What it checks—and what it cannot

- **Scope:** compare changed paths with repository policy.
- **Evidence:** check required proof files and evidence-bundle integrity.
- **Security signals:** flag selected risky source patterns and workflow trust-boundary issues.
- **Documentation and code truth:** detect stale command examples and package-entrypoint drift.
- **Goals and releases:** validate goal dependencies and evaluate release readiness.
- **Agent support:** discover skills, inspect MCP configuration, and install repo-local guidance.

These checks are guardrails, not a sandbox or proof of semantic correctness. Results depend on repository policy and configuration; review findings before treating them as release decisions. Steadfast does not silently rewrite plans or execute the configured pipeline as part of `verify`. Run `steadfast pipeline` separately only after reviewing its manifest.

## Configuration

Run `steadfast init` to create starter governance files. Repository policy lives in `.steadfast/policy.json`; pipeline steps are configured in `.steadfast/pipeline.json`. Treat pipeline manifests as executable configuration and review their commands before running them.

## Project links

- [Source code and issues](https://github.com/rllibo833-sudo/Steadfast)
- [PyPI package](https://pypi.org/project/steadfast-governance/)
- [Changelog](CHANGELOG.md)
- [Adoption and paid pilots](docs/ADOPTION_AND_PAID_PILOT.md)
- [Request an evaluation or collaboration](https://github.com/rllibo833-sudo/Steadfast/issues)

## Development

```bash
python -m pip install -e .
python -m unittest discover -s tests -v
steadfast docs-check
steadfast code-truth
```

MIT licensed. See [LICENSE](LICENSE).
