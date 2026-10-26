# Adopt Steadfast in GitHub Actions

This is the lowest-friction way to evaluate Steadfast on a real repository. It runs on pull requests, publishes a readable report as a workflow artifact, and does not need an AI API key or a Steadfast-hosted service.

## 1. Add the workflow

Copy [the example workflow](../examples/github-actions/steadfast.yml) into your target repository at `.github/workflows/steadfast.yml`.

It installs the published `steadfast-governance` package, runs `steadfast verify`, and uploads the Markdown report even when verification reports a problem. Review the report and workflow permissions before making it a required branch-protection check.

## 2. Start in observation mode

For the first few pull requests, treat results as review signals rather than an automatic merge gate. Check:
- whether findings identify a real issue or just noise;
- whether the repository's policy and evidence expectations fit the team;
- whether the report is useful to the maintainer who must act on it.

Steadfast does not prove code is correct or secure, and its hooks are not a sandbox. Do not upload secrets or confidential source to public issues when sharing feedback.

## 3. Tune only after seeing real results

Run `steadfast init` in a disposable branch or use `steadfast onboard --agent codex` (replace `codex` with `claude`, `cursor`, or `all`) to generate local policy and agent guidance. Review generated files before committing them. Start with one concrete problem; avoid enabling every gate at once.

## 4. Send useful feedback

Open a [collaboration/evaluation issue](https://github.com/rllibo833-sudo/Steadfast/issues/new?template=collaboration.yml) with the workflow you tried, the command, sanitized output, what helped, and what was noisy. Never include tokens, private repository contents, or customer data.

## What adoption success looks like

A successful evaluation means a maintainer outside the Steadfast project has installed it, run it against a real repository, and can point to a useful finding or repeatable workflow. Stars, downloads, and green CI alone are not proof of product-market fit.
