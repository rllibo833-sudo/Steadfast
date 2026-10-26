# Steadfast

**Keep coding agents aligned with the repository's actual state.** Steadfast is a local-first project operations app for repository health checks, evidence-gated task cycles, coding-agent guardrails, and one-click repeatable automations. It includes a local web console and a closed registry of built-in workflow actions. It does not generate code, require an AI API, or send repository contents to a hosted service.

## Quick start

Requires Python 3.10+ and Git.

```bash
python -m pip install -e .
steadfast init
steadfast audit
steadfast scope-check
steadfast evidence-check
steadfast docs-check
steadfast code-truth
steadfast inventory
steadfast goal-check
steadfast release-check
steadfast pipeline --record .steadfast/runs.jsonl
steadfast pipeline-history --limit 20
steadfast findings scan
steadfast findings list --state open --priority high
steadfast findings metrics
steadfast automations list
steadfast automations run quick-health
steadfast automations history
```

The equivalent module entry point is `python -m steadfast`. Initialization is non-destructive: existing policy, goal, and evidence files are never overwritten.

## Commands

- `steadfast init`: create missing policy, goal, and verification-evidence files.
- `steadfast audit [--base REF]`: check changed paths, required evidence, documentation drift, configured repository contracts, and implementation-line budget.
- `steadfast scope-check [--changed PATH ...]`: check explicit paths or the current Git working tree against the allowlist.
- `steadfast evidence-check [--evidence FILE]`: check that required evidence files exist and contain meaningful text. This is a presence check, not proof that a claim is true.
- `steadfast docs-check`: compare CLI command declarations and package entrypoints with project documentation.
- `steadfast code-truth`: derive implementation/test counts, source SHA-256 fingerprints, entrypoint facts and the actual runtime CLI command tree from code/config; fail when documented CLI examples name commands or subcommands that do not exist. Code is authoritative; Markdown is checked against it.
- `steadfast security-check`: scan implementation files for common hardcoded-secret patterns, risky dynamic execution and APIs (including disabled TLS verification and unsafe deserialization), and workflow trust-boundary issues such as untrusted event data interpolated into shell commands. Findings are conservative signals for review, not a full security proof.
- `steadfast pipeline [--manifest FILE] [--workers N] [--record FILE]`: execute a versioned JSON pipeline as a dependency graph; independent steps run concurrently, failed dependencies are skipped, timeouts are bounded, and output is returned as structured JSON. `--record` appends an immutable run summary to JSONL history without overwriting earlier records. Commands use argument arrays with `shell=False`; no shell interpolation is performed.
- `steadfast pipeline-history [--history FILE] [--limit N] [--status all|passed|failed]`: inspect recent pipeline executions, newest first, with outcome filtering. Corrupt complete records are reported rather than silently discarded.
- `steadfast inventory`: produce a deterministic file inventory with SHA-256 digests, file sizes, classification, and budget utilization.
- `steadfast goal-check`: validate Markdown goal metadata, dependencies, cycles, acceptance criteria, and the configured active-goal limit.
- `steadfast release-check`: evaluate release prerequisites without publishing or modifying a release.
- `steadfast baseline-update`: explicitly save the current audit finding baseline.
- `steadfast baseline-check`: compare current findings with the saved baseline and fail on newly introduced findings.
- `steadfast report [--format markdown|json|sarif]`: emit a human-readable report, JSON, or SARIF 2.1.0 for code-scanning integrations.
- `steadfast findings scan`: refresh the durable finding ledger from live audit, goal, security, and workflow checks; newly absent findings are reconciled as resolved, and reappearing resolved findings reopen.
- `steadfast findings list [--state STATE] [--priority PRIORITY] [--query TEXT]`: filter tracked findings by lifecycle state, risk priority, or text.
- `steadfast findings triage ID [--state open|triaged|accepted] [--owner NAME] [--priority LEVEL] [--due-date YYYY-MM-DD]`: preserve assignment and accepted-risk decisions across scans.
- `steadfast findings resolve ID REASON [--false-positive]`: record an explicit resolution; a still-live finding will reopen on the next scan.
- `steadfast findings history [--finding-id ID]`: inspect the tamper-evident finding event chain.
- `steadfast findings metrics`: summarize risk by priority, accepted risk, and overdue items.

Exit codes: `0` no error findings, `1` one or more policy errors or baseline regressions, `2` usage or runtime error. Documentation drift and a missing changelog are warnings rather than automatic failures.

## Policy

Edit `.steadfast/policy.json` to define:

- `allowed_paths`: paths agents may change.
- `documentation_paths`: paths that count as documentation updates.
- `required_evidence`: evidence files that must be present.
- `implementation_paths` and `ignored_paths`: inputs to the product-code line budget.
- `product_code_budget`: maximum counted implementation lines (starter default: 20,000).
- Optional `required_files` and `required_text`: simple repository contracts checked by audit and release readiness.
- `max_active_goals`: limit for simultaneously active goals.

The line count includes nonblank lines that do not begin with `#`; it is a rough budget signal, not a language-aware complexity metric. The 20,000-line target will be pursued through useful capabilities, adapters, parsers, validators, reporting, and integrations—not duplicated or generated filler.

## Verification pipeline

`.steadfast/pipeline.json` defines verification steps with `id`, `command` (an argument array), optional `depends_on`, `cwd`, `timeout`, `env`, and `continue_on_error`. Dependencies are validated before execution; unknown steps and cycles are rejected. Independent steps run concurrently up to the configured worker count. A step timeout is limited to one hour, captured output is bounded, and manifest-provided environment values are redacted from captured output. Treat manifests as executable configuration: review commands before running a pipeline.

## Structured evidence

Use the `steadfast.evidence` module for machine-readable verification records. Each record requires a claim, exact command, integer exit code, result, and ISO-8601 verification timestamp. Optional commit, environment, and limitation fields preserve context. The library validates records and writes files atomically. It does not invent successful outcomes; command execution is handled separately by the explicit, reviewed verification pipeline.

## Goal graph

Place Markdown files in `.steadfast/goals/`. Each file can define `id`, `title`, `status`, and comma-separated `depends_on` fields between YAML-like frontmatter delimiters. Supported states are proposed, ready, active, blocked, done, and cancelled. Include an Acceptance criteria heading with checklist items. The validator detects duplicate IDs, missing dependencies, cycles, active goals blocked by unfinished dependencies, and active-goal limit violations.

## Audit baselines

Baseline snapshots live in `.steadfast/audit-baseline.json`. Creating a baseline is an explicit action; ordinary audit commands never overwrite it. The baseline stores finding fingerprints and code-budget context, then reports newly introduced findings separately from resolved ones. Review the baseline file like any other policy artifact.

## GitHub Actions

Copy `.github/workflows/steadfast.yml` into a repository to run tests and governance checks on GitHub Actions. Before making it a required check, confirm checkout depth and base-ref configuration support the comparisons you want, and tune the allowlist for your repository.

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
steadfast docs-check
```

MIT licensed. See `LICENSE`.

## Coding-agent integrations

`steadfast integrate --agent claude|cursor|codex|all` installs agent-specific instructions and hook configuration. Existing files are preserved by default; use `--overwrite` only when you intend to replace them. `steadfast integration-status` reports installed adapters. `steadfast agent-hook` accepts a JSON event on stdin and emits an allow/block decision based on repository path policy and a small set of destructive-command patterns. The hook never executes the supplied command and is defense-in-depth, not a sandbox; review generated configuration against your installed agent version.

The supported integration targets are Claude Code, Cursor, and Codex. Claude gets a local settings hook and reusable skill; Cursor gets hook configuration and a repository rule; Codex gets an `AGENTS.md` contract and reusable skill. Install them into a target repository with `steadfast --repo /path/to/repo integrate --agent all`.

The local read-only Project Console is available via `steadfast serve` at `http://127.0.0.1:8765` by default. It summarizes governance findings and provides a source-file preview without repository write endpoints.


## Evidence-gated work cycle

Use a goal checklist to track implementation through real verification:

```sh
steadfast --repo . cycle start goal
steadfast --repo . cycle status
steadfast --repo . cycle evidence AC-01 evidence/verification.md --note "Observed behavior"
steadfast --repo . cycle verify
steadfast --repo . cycle complete
steadfast --repo . cycle history
```

The cycle stores the current task in `.steadfast/work-cycle.json` and appends events to `.steadfast/work-cycle.jsonl`. Completion is refused unless the latest configured pipeline and scope check passed, every acceptance criterion has a repository-local evidence file, and each evidence file still matches its recorded SHA-256 digest. File integrity provides traceability, not semantic proof; reviewers must still assess whether the evidence supports the criterion.


### Work cycle in the Project Console

The local Project Console now displays the current work-cycle task, acceptance-evidence coverage, latest verification result, changed paths and recent events. Agent hook responses also include the current cycle status so connected coding agents can keep task context visible while the existing path and destructive-command policy remains in force. The console remains read-only; task changes are made through the `steadfast cycle` CLI.


### Agent completion gate

Claude Code integration also installs a `Stop` hook. When an active Steadfast cycle exists, the hook blocks the agent's completion event until the cycle is marked completed by passing the configured pipeline/scope checks and attaching unchanged evidence files for every acceptance criterion. Repositories without an active cycle retain the existing hook behavior. This gate only enforces the cycle state; it cannot independently judge whether evidence is semantically convincing.


## Finding lifecycle

The finding ledger persists triage metadata across scans in `.steadfast/finding-ledger.json`; transitions are appended to `.steadfast/finding-events.jsonl` as a SHA-256 hash-chained event stream. Findings have stable fingerprints, risk priorities, owner, due date, state, and resolution notes. A scan automatically resolves findings no longer emitted by the current configured checks and reopens them if they return. This is a reconciliation aid, not proof that a fix is correct: the live checks must cover the underlying issue, and accepted risk remains visible in metrics. The Project Console reads the ledger without mutating it.


## Dependency-aware execution planner

Run `steadfast plan` to get the next eligible goals in dependency order, with a transparent heuristic that highlights goals potentially related to open findings. Use `steadfast plan --goal GOAL_ID` to inspect a goal's acceptance criteria and dependencies. Proposed goals are excluded by default; `--include-proposed` shows them in the unready list. The planner is read-only and does not claim to fix findings or automatically change goal status. The Project Console displays the same ready queue.


### Operate the work cycle from the Project Console

Run `steadfast --repo . serve` and open the printed loopback URL. The Work cycle panel can start a configured goal, attach a repository-local evidence file to an acceptance criterion, execute the configured verification pipeline, block a task with a reason, or request completion. The server binds only to loopback and issues a per-process action token; state-changing requests require that token and reject cross-origin requests. The console can change Steadfast's task metadata and journal, but does not edit application source files. A successful HTTP response is not a guarantee that a task passed: inspect the verification result and evidence before completion.


## Local Automation Studio

Run built-in repeatable project workflows without registering for a hosted service or supplying an AI/API key:

- \`quick-health\`: audit, source/workflow security scan, and required-evidence check.
- \`release-review\`: release readiness, security scan, and implementation inventory.
- \`work-queue\`: refresh the finding ledger, calculate risk metrics, and build the dependency-aware next-work queue.

Commands:

\`\`\`sh
steadfast automations list
steadfast automations run quick-health
steadfast automations run release-review
steadfast automations run work-queue
steadfast automations history
steadfast serve
\`\`\`

The Project Console includes an Automation Studio panel with one-click execution and recent-run history. Runs are recorded in \`.steadfast/automation-runs.jsonl\`. Workflows can be customized in \`.steadfast/automations.json\`, but each step must reference a registered built-in action. Workflow files cannot inject shell commands, Python imports, arbitrary URLs, or dynamic expressions. These are project-operations automations, not a general desktop/RPA agent; they do not click arbitrary third-party apps or generate images/videos.


### Run automations from GitHub on a phone

The manual GitHub Actions workflow is named **Steadfast Automation Studio**. From the repository's Actions tab, choose that workflow, tap **Run workflow**, select \`quick-health\`, \`release-review\`, or \`work-queue\`, and start it. The run summary shows the outcome; a JSON artifact contains per-step results and run history. This uses the repository's existing GitHub account and a GitHub-hosted runner; no Termux installation, model API key, or extra third-party account is required. GitHub Actions availability and repository permissions still apply.


Work-cycle verification is tied to a SHA-256 fingerprint of the workspace (excluding Git internals, caches and Steadfast's own runtime journals). If source, configuration, tests or other workspace files change after verification, completion is blocked until the configured pipeline and scope checks are rerun. The Project Console labels such results as stale instead of showing them as current passes.


## Code-first truth check

Run `steadfast code-truth` to see facts derived from the Python implementation, test files, package entrypoints and live argparse command tree. It hashes implementation files and checks documented command examples against actual command names. The JSON report is intended for CI and agent decisions; Markdown is a consumer of these facts, not the canonical record. This check validates command paths and repository structure, not the semantic truth of every sentence or the correctness of business behavior.

For practical agent/skills setup, follow [the coding-agent skills tutorial](docs/AGENT_SKILLS_TUTORIAL.md).


### Agent hook enforcement

Claude Code `PreToolUse` responses use its event-specific `hookSpecificOutput.permissionDecision` schema; Cursor shell hooks use Cursor's native `permission` response schema and inspect the top-level `command` field. Claude-compatible Stop hooks can block a tracked task that has not passed the work-cycle completion gate. Cursor's installed hook set includes shell-command and stop checks with fail-closed hook configuration. Codex currently receives repository instructions and skills, not an equivalent native enforcement hook. See the [Claude Code hook contract](https://docs.anthropic.com/en/docs/claude-code/hooks) and [Cursor hooks contract](https://cursor.com/docs/hooks).


## Agent session ledger

Every valid coding-agent hook event is appended to `.steadfast/agent-sessions.jsonl` with its policy decision, finding codes, session/tool identity, scoped paths, bounded metadata and a SHA-256 hash-chain link. Secret-like fields are redacted and command previews are bounded and redacted; a separate command digest supports correlation without retaining the full command.

```sh
steadfast --repo . sessions list --limit 100
steadfast --repo . sessions list --session-id SESSION_ID
steadfast --repo . sessions verify
```

The Project Console displays recent agent events and allowed/blocked counts. Hook decisions fail closed if an event cannot be recorded. The ledger may contain repository paths and short command previews, so review retention and access before sharing it. Hash chaining detects tampering but is not a digital signature and cannot prevent an attacker with repository write access from rewriting the entire chain.
