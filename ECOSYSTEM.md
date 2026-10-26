# RLI Project Ecosystem

This is a small, independently usable open-source portfolio—not one giant application. Each project solves a different part of the developer workflow, and integrations must be explicit rather than implied.

## The three connected projects

| Project | What it does today | Start here |
|---|---|---|
| **PusingCuk** | Indonesian-keyword programming language, browser playground, compiler/runtime work and Cuk Reality Engine conformance checks. | [Playground](https://rllibo833-sudo.github.io/pusingcuk/playground.html) · [Repository](https://github.com/rllibo833-sudo/pusingcuk) |
| **Mnemos-RLI** | Local-first evidence collection and a living dependency/evidence graph. Its README describes a Supabase-connected knowledge graph branch as a separate deployment/context; credentials and remote writes must be configured by the operator. | [Repository](https://github.com/rllibo833-sudo/mnemos-RLI) |
| **Steadfast** | Repository health, coding-agent guardrails, scoped work orders and evidence-gated verification. | [Repository](https://github.com/rllibo833-sudo/Steadfast) |

## How they fit together

- **PusingCuk produces software** and uses the Cuk Reality Engine to check supported behavior across targets.
- **Mnemos-RLI preserves evidence** about artifacts, dependencies and changes so claims can be traced to observations.
- **Steadfast governs the development process**: define bounded work, inspect repository state and require verification evidence before closing work.

Together, this suggests a practical loop:

1. Use Steadfast to define and scope a concrete change.
2. Build or change the software in its owning repository (for example, PusingCuk).
3. Run that project's own executable conformance checks; do not treat a generic green CI badge as proof of product behavior.
4. Use Mnemos-RLI where artifact/dependency evidence is useful and configured.
5. Link the resulting test output, evidence and release artifact back to the work item.

## Integration truth

The projects remain separate tools today. This page is an ecosystem map, **not a claim that live cross-repository orchestration, shared authentication, a shared Supabase schema, or automatic evidence transfer is already implemented**. No credentials or private database endpoints belong in this repository. Any future adapter must be opt-in, least-privilege, and able to report unavailable services without inventing success.

## A useful first collaboration

Contributors can pick a bounded deliverable: test Steadfast against a real repository, improve PusingCuk's supported-language examples, or improve Mnemos-RLI's evidence graph. Open an issue with the target user, reproduction/evidence, and a concrete acceptance check. No one needs to adopt the whole portfolio to use one project.
