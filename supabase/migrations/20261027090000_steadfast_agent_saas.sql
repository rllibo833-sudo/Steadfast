-- Steadfast SaaS: tenant-scoped agent work, events, and shared knowledge.
create extension if not exists pgcrypto;

create table if not exists public.steadfast_workspaces (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid not null references auth.users(id) on delete cascade,
  name text not null default 'My workspace',
  created_at timestamptz not null default now()
);
create table if not exists public.steadfast_tasks (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references public.steadfast_workspaces(id) on delete cascade,
  created_by uuid not null references auth.users(id) on delete cascade,
  goal text not null check (char_length(goal) between 3 and 4000),
  status text not null default 'queued' check (status in ('queued','running','succeeded','failed','cancelled')),
  plan jsonb not null default '[]'::jsonb,
  result jsonb not null default '{}'::jsonb,
  error text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create table if not exists public.steadfast_task_events (
  id bigint generated always as identity primary key,
  task_id uuid not null references public.steadfast_tasks(id) on delete cascade,
  actor_id uuid references auth.users(id) on delete set null,
  event_type text not null,
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);
create table if not exists public.steadfast_knowledge_nodes (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references public.steadfast_workspaces(id) on delete cascade,
  created_by uuid not null references auth.users(id) on delete cascade,
  node_type text not null default 'fact',
  label text not null check (char_length(label) between 1 and 500),
  content text not null default '',
  source_task_id uuid references public.steadfast_tasks(id) on delete set null,
  confidence numeric(4,3) not null default 0.5 check (confidence between 0 and 1),
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create table if not exists public.steadfast_knowledge_edges (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references public.steadfast_workspaces(id) on delete cascade,
  source_node_id uuid not null references public.steadfast_knowledge_nodes(id) on delete cascade,
  target_node_id uuid not null references public.steadfast_knowledge_nodes(id) on delete cascade,
  relation text not null,
  created_by uuid not null references auth.users(id) on delete cascade,
  created_at timestamptz not null default now(),
  unique (workspace_id, source_node_id, target_node_id, relation),
  check (source_node_id <> target_node_id)
);
create index if not exists steadfast_tasks_workspace_created_idx on public.steadfast_tasks(workspace_id, created_at desc);
create index if not exists steadfast_events_task_created_idx on public.steadfast_task_events(task_id, created_at);
create index if not exists steadfast_nodes_workspace_updated_idx on public.steadfast_knowledge_nodes(workspace_id, updated_at desc);
create index if not exists steadfast_edges_workspace_idx on public.steadfast_knowledge_edges(workspace_id);

alter table public.steadfast_workspaces enable row level security;
alter table public.steadfast_tasks enable row level security;
alter table public.steadfast_task_events enable row level security;
alter table public.steadfast_knowledge_nodes enable row level security;
alter table public.steadfast_knowledge_edges enable row level security;

drop policy if exists steadfast_workspace_owner_all on public.steadfast_workspaces;
create policy steadfast_workspace_owner_all on public.steadfast_workspaces for all to authenticated using (owner_id = auth.uid()) with check (owner_id = auth.uid());

drop policy if exists steadfast_tasks_owner_all on public.steadfast_tasks;
create policy steadfast_tasks_owner_all on public.steadfast_tasks for all to authenticated
using (created_by = auth.uid() and exists (select 1 from public.steadfast_workspaces w where w.id = workspace_id and w.owner_id = auth.uid()))
with check (created_by = auth.uid() and exists (select 1 from public.steadfast_workspaces w where w.id = workspace_id and w.owner_id = auth.uid()));

drop policy if exists steadfast_events_owner_all on public.steadfast_task_events;
create policy steadfast_events_owner_all on public.steadfast_task_events for all to authenticated
using (exists (select 1 from public.steadfast_tasks t join public.steadfast_workspaces w on w.id=t.workspace_id where t.id=task_id and w.owner_id=auth.uid()))
with check (exists (select 1 from public.steadfast_tasks t join public.steadfast_workspaces w on w.id=t.workspace_id where t.id=task_id and w.owner_id=auth.uid()));

drop policy if exists steadfast_nodes_owner_all on public.steadfast_knowledge_nodes;
create policy steadfast_nodes_owner_all on public.steadfast_knowledge_nodes for all to authenticated
using (created_by=auth.uid() and exists (select 1 from public.steadfast_workspaces w where w.id=workspace_id and w.owner_id=auth.uid()))
with check (created_by=auth.uid() and exists (select 1 from public.steadfast_workspaces w where w.id=workspace_id and w.owner_id=auth.uid()));

drop policy if exists steadfast_edges_owner_all on public.steadfast_knowledge_edges;
create policy steadfast_edges_owner_all on public.steadfast_knowledge_edges for all to authenticated
using (created_by=auth.uid() and exists (select 1 from public.steadfast_workspaces w where w.id=workspace_id and w.owner_id=auth.uid()))
with check (created_by=auth.uid() and exists (select 1 from public.steadfast_workspaces w where w.id=workspace_id and w.owner_id=auth.uid()));

grant select, insert, update, delete on public.steadfast_workspaces, public.steadfast_tasks, public.steadfast_task_events, public.steadfast_knowledge_nodes, public.steadfast_knowledge_edges to authenticated;
grant usage, select on all sequences in schema public to authenticated;
