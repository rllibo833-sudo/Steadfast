# Adopt Steadfast in GitHub Actions

Evaluate Steadfast against a real repository before deciding whether it belongs in a required check. The example uses the published PyPI package, needs no AI API key or hosted Steadfast service, and uploads a report for maintainer review.

## Fastest trial

1. Copy [the example workflow](../examples/github-actions/steadfast.yml) into your repository at `.github/workflows/steadfast.yml`.
2. Commit it and open a pull request (or run it manually using **Actions → Steadfast repository checks → Run workflow**).
3. Open the workflow run and download the `steadfast-report-<run-id>` artifact. Review both the JSON verification output and Markdown report.
4. Treat findings as observations for the first few runs. Do not make the check a merge blocker until you have confirmed that the results are useful and understood the failure behavior.

The workflow installs `steadfast-governance` from PyPI and runs `steadfast --repo . verify` followed by `steadfast --repo . report --format markdown`. It uploads available output even when verification fails, then returns a failing job status if verification was not successful. Review the report and permissions before enabling branch protection. The report is a governance signal, not proof that code is correct or secure.

## Evaluate it honestly

For the first few pull requests, record:
- **Actionable:** did it find a real problem the team could fix?
- **Noise:** how many findings were irrelevant or repeated?
- **Fit:** did the default policy match the repository, or require tuning?
- **Cost:** was setup and report review worth the time?
- **Repeatability:** did a later run produce useful, understandable results?

Do not send secrets, private source, customer data, or confidential repository details to public issues. Sanitize logs before sharing them. Steadfast's agent hooks are defense-in-depth, not a sandbox.

## Tune after the baseline

If the trial shows value, run `steadfast init` in a disposable branch or use `steadfast onboard --agent codex` (replace `codex` with `claude`, `cursor`, or `all`). Review generated files before committing. Start with one concrete pain point rather than enabling every gate at once.

## Report the outcome

Open a [collaboration/evaluation issue](https://github.com/rllibo833-sudo/Steadfast/issues/new?template=collaboration.yml). The form records whether the package was installed, whether a real repository was evaluated, which version was used, the outcome, and whether a bounded pilot is of interest. Share sanitized results only.

## Adoption and commercial success criteria

A **completed evaluation** means a maintainer outside the Steadfast project installed it, ran it against a real repository, and recorded whether at least one finding or repeatable workflow was useful. A **pilot** additionally needs an agreed repository, bounded scope, success criteria, and handover. **Paid traction** means a real paid engagement was agreed and payment received—not stars, downloads, commit count, or green CI.

Track these stages from submitted evaluation issues: started → installed → run on real repo → repeated/useful → pilot scoped → paid. Count only evidence submitted by the evaluator; never infer customers from anonymous package downloads. If no outside evaluation has happened yet, report that plainly rather than calling internal CI adoption.
