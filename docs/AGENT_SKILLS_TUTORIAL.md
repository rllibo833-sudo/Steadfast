# Practical tutorial: use Steadfast with coding agents

This guide is an example workflow, not a claim that Steadfast is production-certified. The agent still writes code; Steadfast checks repository policy, real command results, scope and evidence. It does not generate code or make an agent correct by itself.

## 1. Install Steadfast

Clone this repository on a development machine with Python 3.10+ and Git, then install the CLI:

```sh
git clone https://github.com/rllibo833-sudo/Steadfast.git
cd Steadfast
python -m pip install -e .
steadfast --help
steadfast code-truth
```

For a separate project, use the installed `steadfast` command from that project's repository. You do not need an AI API key.

## 2. Initialize the target repository

From the repository you want an agent to change:

```sh
steadfast init
steadfast audit
steadfast code-truth
```

Review `.steadfast/policy.json` and `.steadfast/pipeline.json` before using them. The policy defines allowed paths and evidence requirements. The pipeline is executable configuration: its commands are actually run, so do not run a manifest you have not reviewed.

Set an acceptance checklist in `.steadfast/goal.md` or add a goal file under `.steadfast/goals/`. A work cycle needs a heading named `Acceptance criteria` and checklist items beneath it. Example:

```markdown
## Acceptance criteria
- [ ] The new behavior works for valid input.
- [ ] Invalid input is rejected safely.
- [ ] A regression test covers the behavior.
```

The checklist describes what needs proving; the Markdown itself is not proof that the implementation works.

## 3. Install the agent integration

Run one of these commands against the target repository. Existing files are preserved by default.

```sh
steadfast --repo /path/to/target integrate --agent codex
steadfast --repo /path/to/target integration-status
```

Choose `claude` or `cursor` instead of `codex` for those integrations, or use `--agent all` if all three are intentionally used in the same repository. Inspect every generated file and compare hook configuration with the version of the agent you have installed before relying on it. Use `--overwrite` only when you deliberately want to replace an existing integration file.

Current integration behavior:
- **Codex:** creates an `AGENTS.md` work contract and a reusable Steadfast skill file.
- **Claude Code:** creates local hook settings and a reusable skill file.
- **Cursor:** creates hook settings and a repository rule.

The hook evaluates a JSON tool event and returns allow/block; it never executes the command. Its checks are limited defense-in-depth, not a sandbox, and agent hook protocols can change.

## 4. Add a focused skill to the agent

The repository includes separate skills in `skills/`: `repo-audit`, `scope-guard`, `evidence-check`, `doc-sync`, and `release-readiness`. They are instructions for the agent, while the CLI is the executable check.

For a Codex-style project skill directory, copy the skill you need into the target repository, for example:

```sh
mkdir -p /path/to/target/.agents/skills/repo-audit
cp skills/repo-audit/SKILL.md /path/to/target/.agents/skills/repo-audit/SKILL.md
```

For Claude Code, the corresponding project skill path is typically `.claude/skills/repo-audit/SKILL.md`. Check your installed agent's documentation for its supported skill discovery path. Cursor can use the skill's steps as a project rule, but its rule file format differs; review and adapt the frontmatter rather than assuming the Markdown file is automatically discovered.

A skill tells an agent what to do. It does not enforce the instructions on its own. Use it alongside the CLI, tests and CI.

## 5. Use an evidence-gated task cycle

From the target repository, run:

```sh
steadfast cycle start goal
steadfast cycle status
# Agent implements the feature and adds tests.
steadfast cycle evidence AC-01 evidence/feature-behavior.txt --note "Observed valid-input result"
steadfast cycle evidence AC-02 evidence/invalid-input.txt --note "Observed rejection of invalid input"
steadfast cycle evidence AC-03 tests/test_feature.py --note "Regression test source"
steadfast cycle verify
steadfast cycle complete
```

Replace `AC-01` etc. with the IDs printed by `cycle status`. The evidence paths must be existing repository-local files. `cycle verify` runs the configured pipeline and scope check. Completion is refused if verification failed, evidence is absent or evidence content changed after attachment.

Important: attaching a file records its path and digest; it does not prove that the file's content supports the claim. Review test output and actual behavior. Never use a made-up output transcript as evidence.

## 6. Make code the source of truth

Before claiming a change is complete, run:

```sh
steadfast code-truth
steadfast audit
steadfast security-check
steadfast docs-check
steadfast release-check
steadfast pipeline --record .steadfast/runs.jsonl
```

`code-truth` derives implementation/test counts, source hashes, package entrypoint facts and the runtime CLI command tree from code/configuration. It checks command paths in documented shell examples against the actual CLI. The CI pipeline runs this check so stale command examples can be caught automatically.

This does not yet prove that every prose claim is correct, that tests are comprehensive, or that a static security scan finds every vulnerability. Source hashes prove content identity, not authorship or semantic correctness. Keep tests, executable contracts and observed outputs as primary evidence; update documentation to reflect those results.

## 7. A simple agent prompt

Paste a task-specific request into your coding agent after installing the integration:

> Implement the requested behavior in this repository. First inspect `.steadfast/policy.json`, the active goal and `steadfast code-truth`. Make the smallest integrated product change that meets the acceptance criteria; add or update executable tests. Do not change policy or documentation merely to make checks pass. Run the configured Steadfast pipeline and relevant tests, inspect actual exit codes and outputs, attach real evidence for each acceptance criterion, and request cycle completion only if verification passes. Report changed behavior, files, verification commands and results, and any limitations. Never claim an unrun check passed.

## Limitations to keep in mind

Steadfast is still under active development. The integration hooks are not a security boundary, the code-truth scanner currently validates command examples and structural facts rather than the meaning of all documentation, and acceptance evidence still requires human judgment. Treat CI success as evidence for the checks that ran—not proof that the entire product is mature.
