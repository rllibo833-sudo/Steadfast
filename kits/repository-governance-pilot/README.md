# Repository governance pilot kit

A repeatable, local-first first engagement for a team evaluating Steadfast. This kit is a checklist, not a security certification or a guarantee that findings are complete.

## Outcome

For one repository, deliver:
- a baseline report with findings left intact;
- a short list of high-value fixes tied to an observed workflow;
- a reproducible verification result;
- a portable evidence bundle and a handover note;
- explicit remaining risks and product limitations.

## Before starting

- [ ] The repository owner approves the scope and the person running the checks.
- [ ] Agree on the repository, time window, permitted paths, and one measurable problem.
- [ ] Do not paste source code, secrets, credentials, or private logs into public issues.
- [ ] Record whether this is a community evaluation or a paid engagement; a public issue is not a contract.
- [ ] Read the configured pipeline before running it. Pipeline steps execute repository-configured commands.

## Run locally

From the repository root, after installing Steadfast:

```sh
steadfast --repo . discover
steadfast --repo . verify
steadfast --repo . report --format markdown
steadfast --repo . ecosystem
steadfast --repo . site-check website
```

Run `site-check website` only when the target repository has a `website/` directory; otherwise pass its actual static-site directory or skip that check.

Inspect the JSON/Markdown output. Separate errors from warnings, heuristics from verified facts, and existing findings from regressions. Do not update or suppress the baseline merely to make the report green.

If the repository has a reviewed `.steadfast/pipeline.json`, run:

```sh
steadfast --repo . pipeline --record .steadfast/pilot-runs.jsonl
steadfast --repo . evidence-bundle build
```

Only run a pipeline after reviewing its commands. The evidence bundle is a point-in-time governance snapshot; it is not proof that every source claim is true. Preserve its generated path and verify it with `steadfast --repo . evidence-bundle verify PATH_TO_BUNDLE.zip`.

## Handover template

Record these in the engagement issue or a private customer-approved document:
- Repository and commit inspected:
- Agreed problem and success criteria:
- Commands actually run:
- Exit codes and outcomes:
- Changes made (paths/commit):
- Findings resolved and evidence:
- Findings still open:
- Known limits / checks not run:
- Next recommended action:
- Customer acceptance / follow-up:

## Done means

The pilot is complete only when the agreed deliverables are handed over, commands and outcomes are recorded, unresolved issues are explicit, and the customer can reproduce the result. A green CI badge alone is not proof of adoption, correctness, security, or commercial success.
