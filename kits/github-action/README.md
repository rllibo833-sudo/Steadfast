# Steadfast GitHub Actions integration

Run Steadfast governance checks on pull requests and pushes, without writing a custom workflow step sequence.

## Requirements

- The target repository has Python 3.10+ compatible with the selected Python version.
- Steadfast configuration has been reviewed and committed in the target repository. This action intentionally does **not** run `steadfast init` or mutate repository policy.
- The selected `steadfast-governance` version is available on PyPI.

## Example workflow

Create `.github/workflows/steadfast.yml` in the repository that should be checked:

```yaml
name: Steadfast
on:
  pull_request:
  push:
    branches: [main]

jobs:
  governance:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: rllibo833-sudo/Steadfast/kits/github-action@main
        with:
          python-version: "3.11"
          package-version: "0.4.1"
```

The calling workflow checks out the target repository first. The action installs the pinned package, runs `steadfast verify`, and uploads `steadfast-report.json` as the `steadfast-governance-report` artifact, including on failure when a report can be produced.

## Important behavior

- Pin the action to a reviewed commit SHA or release tag for production workflows instead of relying on `@main`.
- Review `.steadfast/pipeline.json` before running any command that executes its configured pipeline. This action runs `steadfast verify`, not `steadfast pipeline`.
- The action does not publish packages, change baselines, or auto-fix findings.
- This is a reusable composite action hosted in a subdirectory; it is **not yet a GitHub Marketplace listing**.
