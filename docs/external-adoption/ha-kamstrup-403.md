# External adoption trial: `golles/ha-kamstrup_403`

**Run:** [GitHub Actions run #3](https://github.com/rllibo833-sudo/Steadfast/actions/runs/40410708141)  
**Evidence artifact:** [steadfast-external-audit](https://github.com/rllibo833-sudo/Steadfast/actions/runs/40410708141/artifacts/12693286923)  
**Inspected revision:** `d1068e08b1a70ff1f4fa23084eda4e4caffb05cd`  
**Target changes:** none. The policy scaffold and bootstrap commit existed only in the disposable CI checkout.

## Why this repository

The project has publicly asked for a successor maintainer, with the current maintainer indicating that after 1 January 2027 they expect to handle only critical fixes. This is a maintenance-transition candidate, not evidence that the project is abandoned. See [the repository](https://github.com/golles/ha-kamstrup_403) and [maintainer discussion #360](https://github.com/golles/ha-kamstrup_403/issues/360).

## Result

- GitHub Actions trial: **success** (the audit completed and evidence was uploaded).
- `steadfast report --format markdown`: exit code **0**.
- `steadfast verify`: exit code **1**, which indicates findings/policy gates, not a clean verification.
- Report summary: **0 errors, 25 warnings, 0 info**.
- Changed target paths detected: **0**.

The green workflow means the trial pipeline completed; it does **not** mean the target passed every Steadfast policy check. The target has no native Steadfast policy, so the run initialized a temporary scaffold for evaluation. Treat results as a first-pass advisory audit, not a project-approved baseline.

## Findings worth presenting carefully

### 1. Workflow action references (22 warnings)

The analyzer flags action references that use version tags instead of immutable commit SHAs. The target currently uses versioned references such as `actions/checkout@v7.0.1` and `softprops/action-gh-release@v3.0.3`.

**Interpretation:** immutable SHAs improve supply-chain reproducibility and prevent a tag from being moved. Version tags are common and easier to maintain, so this is a hardening recommendation, not proof that any dependency is compromised. Before changing these, verify the upstream action, full commit SHA, and update process.

### 2. Write permissions in release/maintenance workflows (3 warnings)

- [`.github/workflows/license.yaml`](https://github.com/golles/ha-kamstrup_403/blob/main/.github/workflows/license.yaml) requests `contents: write` and `pull-requests: write`; it uses a GitHub App token for the license-year update.
- [`.github/workflows/release-drafter.yaml`](https://github.com/golles/ha-kamstrup_403/blob/main/.github/workflows/release-drafter.yaml) requests `contents: write` to update release drafts.
- [`.github/workflows/release.yaml`](https://github.com/golles/ha-kamstrup_403/blob/main/.github/workflows/release.yaml) requests `contents: write` for release publication.

**Interpretation:** these are workflows that plausibly need write access. The warning is a prompt to review least privilege and token scope, not a confirmed vulnerability. In particular, do not remove required permissions blindly; test the workflow behavior and token boundaries first.

## Limitations

- No source files or workflow files were changed in the target repository.
- No issue or pull request was opened, and no message was sent to the maintainer.
- The run used the published `steadfast-governance` package and a temporary generated policy; this does not yet validate a project-specific policy designed with the maintainer.
- Findings were not independently validated as exploitable vulnerabilities. They are review leads.
- A successful `report` command is distinct from a clean `verify` result.

## Suggested maintainer-facing summary

> I ran a read-only first-pass Steadfast governance audit against a disposable checkout of your repository. It reported 22 advisory warnings for version-tagged GitHub Actions references and 3 warnings for write permissions in release/maintenance workflows. These are hardening review items, not confirmed vulnerabilities; the write permissions appear to support legitimate release or automation behavior. No files in your repository were changed. I can share the evidence and help validate whether any finding merits a change.

## Next validation gate

Before presenting this as a useful adoption case, improve the analyzer's precision around intentional workflow write permissions and make the output distinguish **advisory hardening** from **actionable policy violations**. Then run the same published-package trial on a second independently selected repository and compare the signal-to-noise ratio.
