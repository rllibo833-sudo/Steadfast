# Steadfast adoption and paid-pilot path

This document is the working commercial plan for Steadfast. It is intentionally based on the current product: a local-first repository governance CLI, agent integrations, skills, MCP inspection tools, evidence-gated work orders, and repeatable verification. It does not imply a hosted service, enterprise certification, autonomous code generation, or security guarantees.

## First offer: a repository-governance pilot

**Who it is for:** a small software team or maintainer already using coding agents and worried about scope drift, weak verification, stale documentation, or unclear evidence.

**Deliverable:** one repository assessed with Steadfast, a prioritized findings report, an agreed set of policy/agent integration changes, and a repeatable verification command. The customer keeps the repository and can run the checks locally. No hosted database or source-code upload is required.

**Pilot boundary:**
1. Agree on one repository, one concrete pain point, permitted paths, and a completion date before work starts.
2. Record the current baseline before changing policy or dismissing findings.
3. Run the existing audit, security, site/docs checks as applicable, inventory, and configured pipeline.
4. Implement only the agreed scope; keep all findings and limitations visible.
5. Hand over the diff, commands, results, and follow-up issues. Do not promise zero vulnerabilities or that hooks are a sandbox.

**Commercial rule:** quote a fixed fee only after the scope is understood and accepted by both sides. Do not advertise an invented customer count, certification, SLA, or benchmark. If the maintainer cannot currently accept paid work, offer a clearly labelled community evaluation instead of implying a purchasable service is already staffed.

## Other possible paid work

Offer only after the pilot proves demand:
- **Integration work:** adapt Steadfast to a team's existing coding-agent workflow and CI.
- **Governance setup:** configure repository policy, goals, evidence and verification gates.
- **Maintainer support:** scoped troubleshooting, upgrades and implementation assistance.
- **Sponsored roadmap:** a funder pays for a named capability while the public repository retains its published license and contribution rules.

Keep the core local-first. A hosted dashboard, team database, or usage telemetry is not a prerequisite for the first pilot and should not be built until customers explicitly need it and agree to its data handling.

## Adoption funnel

1. **Try:** a maintainer follows the README quick start on a non-critical repository.
2. **Observe:** they share a sanitized outcome—what check helped, what was noisy, and what failed.
3. **Pilot:** agree on a bounded real workflow and success criteria before implementation.
4. **Convert:** offer paid integration/support only if the pilot removes a real recurring cost.
5. **Expand:** publish reusable kits and anonymized case studies only with permission.

## What counts as evidence of traction

Track these manually in issues or a small local notes file; no database is needed:
- repositories that completed onboarding;
- maintainers who ran the checks and returned feedback;
- accepted collaboration/pilot requests;
- pilots with an agreed scope and a completed handover;
- paid work actually agreed and received;
- integrations contributed by outside maintainers.

Stars, page views, green CI, and feature counts are not revenue or adoption proof.

## Collaboration and outreach

Use the public [collaboration issue form](https://github.com/rllibo833-sudo/Steadfast/issues/new?template=collaboration.yml) to propose a pilot, integration, contribution, or partnership. Do not publish private contact details, secrets, customer source code, or confidential commercial information in public issues.

A first message should be short and specific:
- name the real workflow and problem;
- link to the repository and the relevant command/demo;
- ask for one small evaluation or review;
- state what feedback or contribution would help;
- do not claim a partnership or customer outcome until the other party confirms it.

## Current limits and dependencies

- Steadfast currently runs locally and does not require a hosted database or AI API.
- Its reports are governance signals, not a guarantee of security or correctness.
- Agent hooks are defense-in-depth, not a sandbox.
- A paid pilot needs a willing customer, agreed scope, and a payment method outside this repository. Code changes alone cannot guarantee a sale.
- Before promising paid service, the maintainer must confirm availability, scope, pricing, invoicing/payment method, and support expectations.
