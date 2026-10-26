# Product definition

Steadfast is a local-first repository governance CLI and portable agent toolkit. It inspects a repository against explicit policy, reports security and scope risks, checks verification evidence and documentation alignment, tracks implementation size, validates goal dependencies, compares audit baselines, runs reviewed verification pipelines, and exports machine-readable findings.

## Implemented capabilities

- **Repository audit:** allowlist enforcement, required evidence and file/text contracts, documentation-drift warnings, implementation budget checks, and combined findings.
- **Security review:** secret-pattern scanning with value redaction, risky dynamic execution/API warnings, and GitHub Actions trust-boundary checks.
- **Verification pipeline:** validated JSON dependency graphs, bounded parallel execution, dependency-failure handling, timeouts, output limits, and optional append-only JSONL execution history.
- **Governance data:** deterministic file inventory and SHA-256 digests, structured evidence records, explicit audit baselines, and goal-graph validation.
- **Integration:** CLI and module entry points, Markdown/JSON/SARIF reports, and GitHub Actions-compatible checks.

## Product boundaries

- Local-first: no hosted backend, AI API key, database, or telemetry is required.
- Policy-driven: repository owners configure allowed paths, evidence requirements, and implementation budgets.
- Review-oriented: static findings are signals, not proof of exploitability or semantic correctness. Pipeline manifests execute commands and must be reviewed before use.
- Non-destructive by default: audit commands report findings; baseline replacement is an explicit command.

## Maturity and scope

This is an actively developed implementation, not a claim of production certification. Remaining work includes deeper language-aware security analysis, more complete policy-schema validation, broader integration coverage, and stronger end-to-end release verification. The configured 20,000-line implementation budget is a ceiling/target constraint, not evidence that the codebase already contains 20,000 lines. Growth must come from distinct, integrated capabilities rather than duplicated code or documentation.

## Coding-agent integration and local console

Steadfast can generate policy guidance for Claude Code, Cursor, and Codex, while preserving existing integration files by default. The shared JSON hook checks repository-relative paths against the configured allowlist and blocks selected destructive shell command patterns. It does not execute commands and must be treated as defense-in-depth rather than a sandbox; agent hook schemas vary and should be reviewed against the installed version. The local Project Console provides read-only governance summaries and source previews.


## Evidence-gated work cycle

The cycle binds goal checklist items to repository-local evidence and observed pipeline/scope results. It records task transitions in an append-only JSONL event journal and stores the current task state separately. Completion is refused if verification fails, evidence is missing, or an evidence file changes after attachment. Evidence-file integrity does not establish semantic correctness; the evidence content still requires review.


### Console and agent integration

The Project Console surfaces the work-cycle state and recent journal events alongside audit, security, evidence and release signals. Agent hook responses carry a compact task context (task ID, goal ID and status), and generated skill instructions direct agents to inspect the cycle, attach per-criterion evidence, and run the configured verification gate before completion claims. The hook context is advisory; path and destructive-command findings remain the enforced decisions, and the local console does not mutate repository state.


### Agent completion gate

The Claude Code integration wires a `Stop` hook into the same policy evaluator used for tool events. If a task cycle exists and has not reached `completed`, the completion event is blocked with an actionable reason. A cycle reaches completion only after configured verification and evidence-integrity checks pass. No active cycle means no new completion restriction, preserving use in repositories that have not adopted goal checklists. Hook protocol behavior should still be checked against the installed agent version.


## Finding lifecycle engine

The finding ledger reconciles live audit, goal, security and workflow findings with persistent triage records. Stable fingerprints preserve owner, due date, priority, state and resolution metadata across scans. Disappeared findings are automatically marked resolved; if the same fingerprint returns, the entry is reopened. Explicit resolution requires a reason. Every lifecycle change is appended to a SHA-256 hash-chained JSONL journal whose integrity is checked before additional events are written or history is read. Metrics expose open risk by priority, accepted risk and overdue items. The Project Console renders the latest ledger snapshot read-only; mutation remains an explicit CLI operation. Hash chaining detects edits but is not a signature and cannot prevent a privileged actor from rewriting the entire journal.


## Dependency-aware execution planner

The planner computes a topological ordering of configured goals, reports missing dependencies and cycles, filters goals whose prerequisites are not done, and ranks currently ready goals using a transparent path/token match against open findings. This risk association is heuristic and advisory only. `steadfast plan` and `steadfast plan --goal GOAL_ID` are read-only; implementation and verification still use the work-cycle and configured pipeline.


### Interactive local work-cycle controls

The Project Console supports work-cycle actions for starting a goal, attaching evidence, running the configured pipeline and scope checks, blocking a task, and requesting completion. State-changing HTTP requests are limited to loopback clients and require a random per-process token issued in the HTML response; cross-origin requests are rejected. The console only mutates Steadfast work-cycle state and its event history, not source code. Completion remains governed by the work-cycle evidence and verification checks.


## Local Automation Studio

The console now exposes a one-click workflow runner for repeatable local project operations. Three built-in workflows compose fixed internal actions for quick health, release review, and next-work planning. A JSON manifest may select registered action IDs, but it cannot define shell commands or import arbitrary code. Each run stores per-step outcomes and timestamps in \`.steadfast/automation-runs.jsonl\`. No hosted service, account, or model key is required for these built-in workflows.

This automation scope is intentionally bounded to repository/project operations. It is not yet a general-purpose digital automation system and does not include image/video generation or arbitrary desktop control.


## Phone-accessible execution

The \`.github/workflows/steadfast-automation.yml\` workflow allows a maintainer to start one of the built-in workflows from GitHub's Actions interface, including the mobile website/app. It uses read-only repository permissions, validates the selected workflow against a fixed list, publishes a run summary, and uploads a short-lived JSON artifact. This avoids requiring the user to install Python or run Termux, but it is still a GitHub Actions workflow rather than a standalone hosted SaaS app.


### Verification freshness

A successful pipeline result is not sufficient if the workspace changes afterward. Each work-cycle verification records a deterministic workspace fingerprint; completion compares it with the current workspace and blocks stale results. The console surfaces stale verification. This prevents completion based on a passing run against a different set of files.


## Code-first truth engine

`steadfast code-truth` derives implementation and test inventory from source files, resolves the live CLI tree from the instantiated argparse parser, checks package entrypoints, fingerprints implementation files with SHA-256, and detects documented CLI examples that refer to nonexistent commands or subcommands. The configured CI pipeline runs this check. This deliberately makes code and executable configuration the source of truth; docs are checked as downstream representations. It is not yet semantic verification of arbitrary prose or proof that tests fully cover behavior.

See [the practical coding-agent skills tutorial](AGENT_SKILLS_TUTORIAL.md) for setup and usage examples.


### Agent hook protocol enforcement

Hook adapters emit event-specific response formats instead of one generic JSON shape: Claude Code `PreToolUse` uses `hookSpecificOutput`, Stop uses `decision: block` with a reason, and Cursor shell execution uses `permission: allow|deny`. Cursor's top-level shell command is evaluated by the same destructive-command policy as Claude's nested Bash input. When a tracked cycle exists, Stop/SubagentStop is blocked until the cycle is completed; the message tells the agent to attach acceptance evidence, run verification, and complete the cycle. An absent work cycle is not itself blocked, to avoid trapping untracked sessions. Codex integration remains instruction/skill-based because this implementation does not claim a Codex native hook.


## Agent session evidence

Each valid agent-hook event is recorded in a bounded local JSONL ledger with session/tool identity, policy decision, finding codes, scoped paths, redacted bounded metadata and a hash-chain link. The `sessions` CLI reports per-session activity and verifies chain integrity; the Project Console surfaces recent events. Ledger write failure converts the hook result to a block rather than silently losing the audit trail. The chain is tamper-evident, not signed or immutable against an attacker who can rewrite all repository state.


## Portable evidence bundles

The evidence-bundle engine collects audit, scope/evidence, security, goal, release, inventory, code-truth, documentation-contract, work-cycle, finding-ledger and redacted agent-session results into a portable ZIP. The default bundle contains metadata and file hashes, not source contents. Verification enforces a strict two-entry archive layout, repository-relative paths, compressed/uncompressed size limits, schema checks and payload SHA-256 integrity. The manifest is not signed; hash integrity must not be represented as producer authentication. Unavailable component checks remain explicitly unavailable rather than being counted as passes.


## Change impact analysis

The change-impact engine maps modified paths to source, test, documentation, workflow, configuration and sensitive-path classes. It detects conventional source/test pairing gaps, identifies public-surface changes without documentation updates, proposes review gates and computes a bounded triage score with explicit factors and limitations. Sensitive-looking credential paths block a passing result. Other path relationships remain advisory because naming conventions cannot prove semantic coupling or actual test assertions. The engine is exposed as `impact-check` and is included in work-cycle verification and evidence bundles.
