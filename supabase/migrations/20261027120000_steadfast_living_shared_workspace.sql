-- Create one shared Steadfast knowledge workspace and enroll every existing/new account.
-- Only explicitly selected, concise insights are written into this graph; task history stays in Steadfast tables.
create or replace function public.ensure_steadfast_living_shared_member()
returns trigger
language plpgsql
security definer
set search_path = public, auth
as $$
declare
  shared_id uuid;
begin
  select id into shared_id from public.knowledge_workspaces
  where name = 'Steadfast Living Shared' order by created_at asc limit 1;

  if shared_id is null then
    insert into public.knowledge_workspaces (name, owner_id)
    values ('Steadfast Living Shared', new.id) returning id into shared_id;
    insert into public.knowledge_workspace_members (workspace_id, user_id, role)
    values (shared_id, new.id, 'admin') on conflict (workspace_id, user_id) do nothing;
  else
    insert into public.knowledge_workspace_members (workspace_id, user_id, role)
    values (shared_id, new.id, 'writer') on conflict (workspace_id, user_id) do nothing;
  end if;
  return new;
end;
$$;

do $$
declare
  first_user_id uuid;
  shared_id uuid;
  user_row record;
begin
  select id into first_user_id from auth.users order by created_at asc limit 1;
  if first_user_id is null then return; end if;
  select id into shared_id from public.knowledge_workspaces
  where name = 'Steadfast Living Shared' order by created_at asc limit 1;
  if shared_id is null then
    insert into public.knowledge_workspaces (name, owner_id)
    values ('Steadfast Living Shared', first_user_id) returning id into shared_id;
  end if;
  for user_row in select id from auth.users loop
    insert into public.knowledge_workspace_members (workspace_id, user_id, role)
    values (shared_id, user_row.id, case when user_row.id = first_user_id then 'admin' else 'writer' end)
    on conflict (workspace_id, user_id) do nothing;
  end loop;
end;
$$;

drop trigger if exists steadfast_living_shared_membership on auth.users;
create trigger steadfast_living_shared_membership
after insert on auth.users
for each row execute function public.ensure_steadfast_living_shared_member();
