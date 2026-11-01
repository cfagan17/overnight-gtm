-- 0004 Runtime primitives: runs and skills
--
-- The primitives in 0003 record what the company knows. These record how the agents
-- worked. A run is one agent session (model, prompt version, skills loaded, every tool
-- call). Every decision belongs to a run, so any ledger change can be traced to the
-- exact model, prompt and skill versions that made it. This is the same idea as
-- linking an agent session to the git commit it produced, applied to GTM data.

create table public.runs (
  id bigint generated always as identity primary key,
  agent_definition_id bigint not null references public.agent_definitions(id),
  principal_id uuid not null,
  loop text not null,
  model text not null,
  prompt_version text not null,
  skill_versions jsonb not null default '{}'::jsonb,   -- {"account-plan": 3, "meddpicc": 1}
  autonomy_level smallint not null,                      -- the loop's level when the run started
  trigger text,                                          -- what started it
  status text not null default 'running' check (status in ('running','completed','failed')),
  transcript_uri text,
  tokens_in int,
  tokens_out int,
  started_at timestamptz not null default now(),
  ended_at timestamptz
);

-- Written by capture hooks: the runner, or a Claude Code PostToolUse hook.
create table public.run_events (
  run_id bigint not null references public.runs(id),
  seq int not null,
  event_type text not null check (event_type in ('model_turn','tool_call','tool_result','hook','error')),
  name text,
  payload jsonb not null default '{}'::jsonb,
  at timestamptz not null default now(),
  primary key (run_id, seq)
);

alter table public.decisions add constraint decisions_run_fk foreign key (run_id) references public.runs(id);
alter table public.evidence add constraint evidence_run_fk foreign key (run_id) references public.runs(id);

-- Skills: versioned instruction files agents load (methodology, stage definitions, plays).
create table public.skills (
  name text not null,
  version int not null,
  body text not null,
  status text not null default 'proposed' check (status in ('proposed','approved','retired','rejected')),
  proposed_by uuid not null,
  proposed_decision_id bigint references public.decisions(id),
  approved_by uuid,
  approved_at timestamptz,
  primary key (name, version)
);
create unique index skills_one_approved on public.skills (name) where status = 'approved';

alter table public.runs enable row level security;
alter table public.run_events enable row level security;
alter table public.skills enable row level security;

create policy ea_runs_select on public.runs for select to authenticated
  using (principal_id = auth.uid() or ea_private.current_role_name() in ('owner','manager','readonly'));
create policy ea_run_events_select on public.run_events for select to authenticated
  using (exists (select 1 from public.runs r where r.id = run_id));
create policy ea_skills_select on public.skills for select to authenticated
  using (ea_private.current_role_name() <> 'none');

grant select on public.runs, public.run_events, public.skills to authenticated;
grant all on public.runs, public.run_events, public.skills to service_role;
grant usage, select on all sequences in schema public to authenticated, service_role;

create trigger ea_audit after insert or update or delete on public.skills
  for each row execute function ea_private.audit();

-- Agent accounts --------------------------------------------------------------------
-- Agents sign in as their own Supabase auth user. Atomic's handle_new_user trigger gives
-- every new auth user a row in sales (the seller directory). Agents are not sellers, so
-- when a new auth user is marked {"ea_kind": "agent"} in app metadata, that row is
-- removed right after Atomic creates it. (Triggers fire in name order:
-- on_auth_user_created, then on_auth_user_created_ea.)
create or replace function ea_private.on_auth_user_created() returns trigger
language plpgsql security definer set search_path = '' as $$
begin
  if new.raw_app_meta_data->>'ea_kind' = 'agent' then
    delete from public.sales where user_id = new.id;
  end if;
  return new;
end $$;
create trigger on_auth_user_created_ea after insert on auth.users
  for each row execute function ea_private.on_auth_user_created();
