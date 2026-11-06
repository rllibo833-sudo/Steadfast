-- Central business operations foundation.
-- Additive only: this migration does not activate projects, deploy services, or store credentials.
create extension if not exists pgcrypto;

create table if not exists public.steadfast_approvals (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references public.steadfast_workspaces(id) on delete cascade,
  task_id uuid references public.steadfast_tasks(id) on delete set null,
  requested_by uuid not null references auth.users(id) on delete cascade,
  action_type text not null check (action_type in (
    'publish_content','send_customer_message','submit_registration','make_payment',
    'deploy_production','change_production_data','connect_integration','other'
  )),
  target text not null check (char_length(target) between 1 and 500),
  summary text not null check (char_length(summary) between 1 and 4000),
  payload jsonb not null default '{}'::jsonb,
  status text not null default 'pending' check (status in (
    'pending','approved','rejected','expired','executed','failed','cancelled'
  )),
  idempotency_key text not null,
  expires_at timestamptz not null default (now() + interval '7 days'),
  decided_by uuid references auth.users(id) on delete set null,
  decided_at timestamptz,
  decision_note text,
  executed_at timestamptz,
  execution_ref text,
  execution_result jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (workspace_id, idempotency_key),
  check ((status not in ('approved','rejected')) or (decided_by is not null and decided_at is not null))
);

create table if not exists public.steadfast_integrations (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references public.steadfast_workspaces(id) on delete cascade,
  provider text not null check (provider in (
    'google','gmail','meta','instagram','whatsapp','windsor_ai','supabase',
    'github','cloudflare','vps','search_console','other'
  )),
  display_name text not null,
  account_hint text,
  status text not null default 'unverified' check (status in (
    'unverified','connected','degraded','disconnected','reauthorization_required'
  )),
  capabilities jsonb not null default '[]'::jsonb,
  secret_reference text,
  last_checked_at timestamptz,
  last_success_at timestamptz,
  last_error_code text,
  last_error_summary text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (workspace_id, provider, display_name)
);
comment on column public.steadfast_integrations.secret_reference is
  'Pointer to an external secret manager only; never store tokens, passwords, or secret values in this table.';

create table if not exists public.steadfast_audit_log (
  id bigint generated always as identity primary key,
  workspace_id uuid not null references public.steadfast_workspaces(id) on delete cascade,
  actor_id uuid references auth.users(id) on delete set null,
  task_id uuid references public.steadfast_tasks(id) on delete set null,
  approval_id uuid references public.steadfast_approvals(id) on delete set null,
  event_type text not null,
  resource_type text not null,
  resource_id text,
  outcome text not null default 'recorded',
  details jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists steadfast_approvals_queue_idx
  on public.steadfast_approvals(workspace_id, status, created_at desc);
create index if not exists steadfast_approvals_task_idx
  on public.steadfast_approvals(task_id, created_at desc);
create index if not exists steadfast_integrations_status_idx
  on public.steadfast_integrations(workspace_id, status, provider);
create index if not exists steadfast_audit_workspace_created_idx
  on public.steadfast_audit_log(workspace_id, created_at desc);

alter table public.steadfast_approvals enable row level security;
alter table public.steadfast_integrations enable row level security;
alter table public.steadfast_audit_log enable row level security;

drop policy if exists steadfast_approvals_owner_select on public.steadfast_approvals;
create policy steadfast_approvals_owner_select on public.steadfast_approvals
  for select to authenticated
  using (exists (
    select 1 from public.steadfast_workspaces w
    where w.id = workspace_id and w.owner_id = auth.uid()
  ));

drop policy if exists steadfast_approvals_owner_insert on public.steadfast_approvals;
create policy steadfast_approvals_owner_insert on public.steadfast_approvals
  for insert to authenticated
  with check (
    requested_by = auth.uid() and exists (
      select 1 from public.steadfast_workspaces w
      where w.id = workspace_id and w.owner_id = auth.uid()
    )
  );

drop policy if exists steadfast_approvals_owner_update on public.steadfast_approvals;
create policy steadfast_approvals_owner_update on public.steadfast_approvals
  for update to authenticated
  using (exists (
    select 1 from public.steadfast_workspaces w
    where w.id = workspace_id and w.owner_id = auth.uid()
  ))
  with check (exists (
    select 1 from public.steadfast_workspaces w
    where w.id = workspace_id and w.owner_id = auth.uid()
  ));

drop policy if exists steadfast_integrations_owner_all on public.steadfast_integrations;
create policy steadfast_integrations_owner_all on public.steadfast_integrations
  for all to authenticated
  using (exists (
    select 1 from public.steadfast_workspaces w
    where w.id = workspace_id and w.owner_id = auth.uid()
  ))
  with check (exists (
    select 1 from public.steadfast_workspaces w
    where w.id = workspace_id and w.owner_id = auth.uid()
  ));

drop policy if exists steadfast_audit_owner_select on public.steadfast_audit_log;
create policy steadfast_audit_owner_select on public.steadfast_audit_log
  for select to authenticated
  using (exists (
    select 1 from public.steadfast_workspaces w
    where w.id = workspace_id and w.owner_id = auth.uid()
  ));

drop policy if exists steadfast_audit_owner_insert on public.steadfast_audit_log;
create policy steadfast_audit_owner_insert on public.steadfast_audit_log
  for insert to authenticated
  with check (
    (actor_id is null or actor_id = auth.uid()) and exists (
      select 1 from public.steadfast_workspaces w
      where w.id = workspace_id and w.owner_id = auth.uid()
    )
  );

grant select, insert, update on public.steadfast_approvals to authenticated;
grant select, insert, update, delete on public.steadfast_integrations to authenticated;
grant select, insert on public.steadfast_audit_log to authenticated;
grant usage, select on sequence public.steadfast_audit_log_id_seq to authenticated;
