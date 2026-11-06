# Central operations foundation

This repository uses the existing Supabase task/event foundation and GitHub Actions. The central operations layer is additive and does not require another Cloudflare Worker.

## Current architecture

- `steadfast_workspaces`, `steadfast_tasks`, and `steadfast_task_events` are the existing tenant-scoped task and event foundation.
- `steadfast_approvals` records owner decisions for externally visible or high-impact actions.
- `steadfast_integrations` records provider identity, verified status, safe capabilities, health checks, and an optional secret-manager reference. It must never contain token or password values.
- `steadfast_audit_log` records actor, task, approval, target resource, outcome, and timestamp.
- Existing GitHub Actions remains the scheduled execution surface. No new Worker or Workers AI dependency is introduced.

## Action policy

Automatic/read-only: inventory, health checks, draft generation, SEO analysis, inbox classification, and reporting where a verified read connection exists.

Approval required for each concrete action: publishing public content, sending WhatsApp/customer messages, submitting forms or registrations, payments, production deployment, destructive database changes, and granting new integration permissions. Approval is scoped to one action payload and expires after seven days.

## Integration verification

A provider is not considered connected because an account was linked elsewhere or because a provider name is present in configuration. Mark it `connected` only after a safe authenticated API read/test succeeds. Store only a secret-manager reference in the integration registry; never persist credentials in SQL rows, repository files, issue comments, logs, or chat.

## Rollout order

1. Apply the additive migration only after identifying and explicitly approving the intended active Supabase project.
2. Create the owner's workspace and verify row-level security using an authenticated owner session.
3. Connect/read-test Gmail/identity and existing Windsor.ai data path without repeating account linking.
4. Add Instagram Professional and WhatsApp Business Cloud API read capabilities; request write scopes only when needed and keep sending/publishing approval-gated.
5. Add VPS/deployment inventory and health checks, then SEO/content workflows.
6. Build the owner control panel against tasks, approvals, integration health, and audit events.

## Current limitation

The Supabase projects previously visible to the connected account were inactive. Therefore this migration is repository code only until the owner-selected project is active and explicitly approved for schema changes. No production database or external account is changed by this branch.
