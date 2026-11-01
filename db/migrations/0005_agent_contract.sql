-- 0005 The agent contract
--
-- Agents never get SQL. They get a short list of functions. Each write function checks,
-- inside Postgres, before it does anything:
--
--   * the caller is the agent that owns the run          (require_run)
--   * the agent has an approved grant for this tool        (require_tool)
--   * the loop's autonomy level allows this action         (require_level)
--   * the record is inside the agent's scope               (can_see_subject / agent scope)
--   * policies allow it, and the account is not in a holdout
--   * a ledger change cites a decision that cites strong evidence
--
-- Because agents cannot write tables directly (RLS write policies require a human,
-- see 0002), a bug in a prompt or an agent framework cannot skip these checks.
--
-- Autonomy levels
--   0 observe        read, record evidence
--   1 suggest        propose decisions, strategies, commitments, skill edits
--   2 act w/approval queue field updates and touches; a human approves each one
--   3 act and report apply allowed field updates and schedule touches directly
--   4 autonomous     same as 3 inside policy; humans audit samples

-- Supporting tables ------------------------------------------------------------------

create table public.field_update_allowlist (
  table_name text not null,
  field text not null,
  min_level smallint not null default 3 check (min_level between 2 and 4),
  primary key (table_name, field)
);
insert into public.field_update_allowlist (table_name, field, min_level) values
  ('deals', 'stage', 3),
  ('deals', 'expected_closing_date', 3),
  ('deals', 'description', 3),
  ('contacts', 'title', 3),
  ('contacts', 'background', 3),
  ('companies', 'segment', 3),
  ('companies', 'description', 3);
-- Deliberately absent: amounts, owners, territories, forecast_category. Money, credit and
-- the forecast call stay with humans.

create table public.touches (
  id bigint generated always as identity primary key,
  decision_id bigint not null references public.decisions(id),
  run_id bigint references public.runs(id),
  contact_id bigint not null references public.contacts(id),
  channel text not null check (channel in ('email','call','linkedin','meeting','partner_intro','sms','event')),
  sender_type text not null check (sender_type in ('agent','rep','executive','partner','se')),
  purpose text not null,
  content_ref text,
  scheduled_for timestamptz,
  status text not null check (status in ('pending_approval','scheduled','sent','cancelled','blocked')),
  blocked_reason text,
  created_at timestamptz not null default now()
);
create index touches_contact_idx on public.touches (contact_id, created_at desc);

create table public.escalations (
  id bigint generated always as identity primary key,
  run_id bigint references public.runs(id),
  subject_type text not null,
  subject_id text not null,
  to_user uuid not null,
  reason text not null,
  status text not null default 'open' check (status in ('open','closed')),
  created_at timestamptz not null default now()
);

alter table public.field_update_allowlist enable row level security;
alter table public.touches enable row level security;
alter table public.escalations enable row level security;
create policy ea_allowlist_select on public.field_update_allowlist for select to authenticated using (true);
create policy ea_touches_select on public.touches for select to authenticated
  using (ea_private.can_see_contact(contact_id));
create policy ea_escalations_select on public.escalations for select to authenticated
  using (to_user = auth.uid() or ea_private.current_role_name() in ('owner','manager'));
create policy ea_escalations_update on public.escalations for update to authenticated
  using (ea_private.is_human() and to_user = auth.uid()) with check (ea_private.is_human() and to_user = auth.uid());
grant select on public.field_update_allowlist, public.touches, public.escalations to authenticated;
grant update (status) on public.escalations to authenticated;
grant all on public.field_update_allowlist, public.touches, public.escalations to service_role;
grant usage, select on all sequences in schema public to authenticated, service_role;
create trigger ea_audit after insert or update or delete on public.touches
  for each row execute function ea_private.audit();

-- Guards -----------------------------------------------------------------------------

create or replace function ea_private.raise_denied(p_msg text) returns void
language plpgsql set search_path = '' as $$
begin
  raise exception 'ea: %', p_msg using errcode = '42501';
end $$;

-- Returns the run if the caller is the agent that owns it and it is still running.
create or replace function ea_private.require_run(p_run_id bigint) returns public.runs
language plpgsql stable security definer set search_path = '' as $$
declare r public.runs;
begin
  select * into r from public.runs where id = p_run_id;
  if r.id is null then perform ea_private.raise_denied('run not found'); end if;
  if r.principal_id is distinct from auth.uid() then perform ea_private.raise_denied('run belongs to another principal'); end if;
  if r.status <> 'running' then perform ea_private.raise_denied('run is not running'); end if;
  if not exists (select 1 from public.agent_definitions d where d.id = r.agent_definition_id and d.active) then
    perform ea_private.raise_denied('agent definition inactive');
  end if;
  return r;
end $$;

create or replace function ea_private.require_tool(p_tool text) returns void
language plpgsql stable security definer set search_path = '' as $$
begin
  if not exists (select 1 from public.agent_grants g
                 where g.agent_definition_id = ea_private.current_agent_definition_id()
                   and g.tool = p_tool and g.approved_at is not null) then
    perform ea_private.raise_denied(format('tool %s not granted to this agent', p_tool));
  end if;
end $$;

-- The effective level is the lower of the level when the run started and the level now,
-- so a demotion takes effect mid-run and a promotion waits for the next run.
create or replace function ea_private.effective_level(p_run public.runs) returns smallint
language sql stable security definer set search_path = '' as $$
  select least(p_run.autonomy_level, d.autonomy_level)::smallint
  from public.agent_definitions d where d.id = p_run.agent_definition_id
$$;

create or replace function ea_private.require_level(p_run public.runs, p_min smallint, p_what text) returns smallint
language plpgsql stable security definer set search_path = '' as $$
declare v smallint := ea_private.effective_level(p_run);
begin
  if v < p_min then
    perform ea_private.raise_denied(format('%s needs autonomy level %s, loop %s is at %s', p_what, p_min, p_run."loop", v));
  end if;
  return v;
end $$;

-- Agents are only ever callers through these functions; humans may call some of them.
create or replace function ea_private.agent_or_human(p_run_id bigint, p_tool text, p_min smallint, p_what text,
  out run public.runs, out level smallint)
language plpgsql security definer set search_path = '' as $$
begin
  if ea_private.current_kind() = 'agent' then
    if p_run_id is null then perform ea_private.raise_denied('agents must pass their run id'); end if;
    run := ea_private.require_run(p_run_id);
    perform ea_private.require_tool(p_tool);
    level := ea_private.require_level(run, p_min, p_what);
  elsif ea_private.current_kind() = 'human' then
    if p_run_id is not null then perform ea_private.raise_denied('humans do not act inside agent runs'); end if;
    level := 4;
  else
    perform ea_private.raise_denied('caller is not a known principal');
  end if;
end $$;

create or replace function ea_private.in_holdout(p_loop text, p_subject_type text, p_subject_id text) returns boolean
language sql stable security definer set search_path = '' as $$
  select exists (
    select 1 from public.experiments e
    join public.experiment_assignments a on a.experiment_id = e.id
    where e.status = 'running' and e."loop" = p_loop and e.subject_type = p_subject_type
      and a.subject_id = p_subject_id and a.arm = 'holdout'
  )
$$;

-- Runs ---------------------------------------------------------------------------------

create or replace function public.start_run(p_model text, p_prompt_version text,
  p_skill_versions jsonb default '{}'::jsonb, p_trigger text default null)
returns bigint language plpgsql security definer set search_path = '' as $$
declare v_def public.agent_definitions; v_id bigint;
begin
  if ea_private.current_kind() <> 'agent' then perform ea_private.raise_denied('only agents start runs'); end if;
  select * into v_def from public.agent_definitions where id = ea_private.current_agent_definition_id();
  if v_def.id is null or not v_def.active then perform ea_private.raise_denied('agent definition inactive'); end if;
  insert into public.runs (agent_definition_id, principal_id, loop, model, prompt_version, skill_versions, autonomy_level, trigger)
  values (v_def.id, auth.uid(), v_def."loop", p_model, p_prompt_version, coalesce(p_skill_versions, '{}'::jsonb), v_def.autonomy_level, p_trigger)
  returning id into v_id;
  return v_id;
end $$;

create or replace function public.end_run(p_run_id bigint, p_status text default 'completed',
  p_transcript_uri text default null, p_tokens_in int default null, p_tokens_out int default null)
returns void language plpgsql security definer set search_path = '' as $$
begin
  perform ea_private.require_run(p_run_id);
  if p_status not in ('completed','failed') then perform ea_private.raise_denied('status must be completed or failed'); end if;
  update public.runs set status = p_status, transcript_uri = p_transcript_uri,
    tokens_in = p_tokens_in, tokens_out = p_tokens_out, ended_at = now()
  where id = p_run_id;
end $$;

-- Capture hook target: one call per model turn, tool call or tool result.
create or replace function public.record_run_event(p_run_id bigint, p_event_type text, p_name text default null,
  p_payload jsonb default '{}'::jsonb)
returns int language plpgsql security definer set search_path = '' as $$
declare v_seq int;
begin
  perform ea_private.require_run(p_run_id);
  perform pg_advisory_xact_lock(p_run_id);
  select coalesce(max(seq), 0) + 1 into v_seq from public.run_events where run_id = p_run_id;
  insert into public.run_events (run_id, seq, event_type, name, payload)
  values (p_run_id, v_seq, p_event_type, p_name, coalesce(p_payload, '{}'::jsonb));
  return v_seq;
end $$;

-- Reads (security invoker: row-level security decides what comes back) ----------------

create or replace function public.get_account_context(p_company_id bigint, p_run_id bigint default null)
returns jsonb language plpgsql stable security invoker set search_path = '' as $$
declare v jsonb;
begin
  if ea_private.current_kind() = 'agent' then
    perform ea_private.require_run(p_run_id);
    perform ea_private.require_tool('get_account_context');
  end if;
  if not exists (select 1 from public.companies where id = p_company_id) then
    perform ea_private.raise_denied('company not found or not visible');
  end if;
  select jsonb_build_object(
    'company', (select to_jsonb(c) - 'logo' from public.companies c where c.id = p_company_id),
    'contacts', coalesce((select jsonb_agg(jsonb_build_object('id', ct.id, 'name', concat_ws(' ', ct.first_name, ct.last_name),
                    'title', ct.title, 'status', ct.status,
                    'do_not_contact', exists (select 1 from public.do_not_contact x where x.contact_id = ct.id)))
                 from public.contacts ct where ct.company_id = p_company_id), '[]'),
    'open_deals', coalesce((select jsonb_agg(jsonb_build_object('id', d.id, 'name', d.name, 'stage', d.stage,
                    'amount', d.amount, 'forecast_category', d.forecast_category, 'expected_closing_date', d.expected_closing_date,
                    'partners', (select jsonb_agg(jsonb_build_object('partner_id', dp.partner_id, 'credit', dp.credit))
                                 from public.deal_partners dp where dp.deal_id = d.id)))
                 from public.deals d where d.company_id = p_company_id and d.archived_at is null), '[]'),
    'contracts', coalesce((select jsonb_agg(to_jsonb(k)) from public.contracts k where k.company_id = p_company_id), '[]'),
    'evidence', coalesce((select jsonb_agg(jsonb_build_object('id', e.id, 'kind', e.kind, 'strength', e.strength,
                    'claim', e.claim, 'source_uri', e.source_uri, 'observed_at', e.observed_at) order by e.observed_at desc)
                 from (select * from public.evidence e
                       where e.superseded_by is null
                         and ((e.subject_type = 'company' and e.subject_id = p_company_id::text)
                           or (e.subject_type = 'contact' and e.subject_id in (select id::text from public.contacts where company_id = p_company_id))
                           or (e.subject_type = 'deal' and e.subject_id in (select id::text from public.deals where company_id = p_company_id)))
                       order by e.observed_at desc limit 50) e), '[]'),
    'strategies', coalesce((select jsonb_agg(jsonb_build_object('id', s.id, 'version', s.version, 'status', s.status,
                    'plan', s.plan, 'review_outcome', dd.review_outcome, 'review_note', dd.review_note,
                    'edited_payload', dd.edited_payload) order by s.version desc)
                 from (select * from public.strategies s where s.subject_type = 'company' and s.subject_id = p_company_id::text
                       order by s.version desc limit 3) s
                 left join public.decisions dd on dd.id = s.decision_id), '[]'),
    'open_commitments', coalesce((select jsonb_agg(to_jsonb(m)) from public.commitments m
                 where m.subject_type = 'company' and m.subject_id = p_company_id::text and m.status = 'open'), '[]'),
    'in_holdout_for', coalesce((select jsonb_agg(e."loop") from public.experiments e
                 join public.experiment_assignments a on a.experiment_id = e.id
                 where e.status = 'running' and e.subject_type = 'company'
                   and a.subject_id = p_company_id::text and a.arm = 'holdout'), '[]')
  ) into v;
  return v;
end $$;

create or replace function public.search_evidence(p_subject_type text, p_subject_id text,
  p_kinds text[] default null, p_since timestamptz default null, p_limit int default 50, p_run_id bigint default null)
returns setof public.evidence language plpgsql stable security invoker set search_path = '' as $$
begin
  if ea_private.current_kind() = 'agent' then
    perform ea_private.require_run(p_run_id);
    perform ea_private.require_tool('search_evidence');
  end if;
  return query
    select e.* from public.evidence e
    where e.subject_type = p_subject_type and e.subject_id = p_subject_id
      and e.superseded_by is null
      and (p_kinds is null or e.kind = any (p_kinds))
      and (p_since is null or e.observed_at >= p_since)
    order by e.observed_at desc
    limit least(greatest(coalesce(p_limit, 50), 1), 200);
end $$;

create or replace function public.get_policies(p_contact_id bigint default null, p_run_id bigint default null)
returns jsonb language plpgsql stable security invoker set search_path = '' as $$
declare v_company bigint;
begin
  if ea_private.current_kind() = 'agent' then
    perform ea_private.require_run(p_run_id);
    perform ea_private.require_tool('get_policies');
  end if;
  select company_id into v_company from public.contacts where id = p_contact_id;
  return jsonb_build_object(
    'policies', coalesce((select jsonb_agg(jsonb_build_object('name', p.name, 'rule_type', p.rule_type, 'params', p.params))
                          from public.policies p where p.active), '[]'),
    'contact', case when p_contact_id is null then null else jsonb_build_object(
       'do_not_contact', exists (select 1 from public.do_not_contact x where x.contact_id = p_contact_id),
       'touches_last_14d', (select count(*) from public.touches t where t.contact_id = p_contact_id
                            and t.status in ('scheduled','sent') and t.created_at > now() - interval '14 days'),
       'partner_credit_on_account', coalesce((select jsonb_agg(distinct dp.credit) from public.deal_partners dp
                            join public.deals d on d.id = dp.deal_id where d.company_id = v_company), '[]')) end
  );
end $$;

-- Writes -----------------------------------------------------------------------------

create or replace function public.record_evidence(p_run_id bigint, p_subject_type text, p_subject_id text,
  p_kind text, p_claim text, p_source_uri text, p_observed_at timestamptz)
returns bigint language plpgsql security definer set search_path = '' as $$
declare a record; v_run public.runs; v_id bigint;
begin
  select * into a from ea_private.agent_or_human(p_run_id, 'record_evidence', 0::smallint, 'record_evidence');
  v_run := a.run;
  if not ea_private.can_see_subject(p_subject_type, p_subject_id) then
    perform ea_private.raise_denied('subject not visible to caller');
  end if;
  if p_observed_at > now() + interval '5 minutes' then perform ea_private.raise_denied('observed_at is in the future'); end if;
  insert into public.evidence (subject_type, subject_id, kind, claim, source_uri, observed_at, strength, recorded_by, run_id)
  values (p_subject_type, p_subject_id, p_kind, p_claim, p_source_uri, p_observed_at, 'weak', auth.uid(), p_run_id)
  returning id into v_id;
  return v_id;
end $$;

create or replace function public.supersede_evidence(p_run_id bigint, p_old_id bigint, p_new_id bigint)
returns void language plpgsql security definer set search_path = '' as $$
declare a record; v_run public.runs; o public.evidence; n public.evidence;
begin
  select * into a from ea_private.agent_or_human(p_run_id, 'record_evidence', 0::smallint, 'supersede_evidence');
  v_run := a.run;
  select * into o from public.evidence where id = p_old_id;
  select * into n from public.evidence where id = p_new_id;
  if o.id is null or n.id is null or o.subject_type <> n.subject_type or o.subject_id <> n.subject_id
     or not ea_private.can_see_subject(o.subject_type, o.subject_id) then
    perform ea_private.raise_denied('both evidence rows must exist, be visible and share a subject');
  end if;
  update public.evidence set superseded_by = p_new_id where id = p_old_id;
end $$;

create or replace function public.propose_decision(p_run_id bigint, p_action text, p_subject_type text, p_subject_id text,
  p_rationale text, p_evidence_ids bigint[], p_payload jsonb default '{}'::jsonb)
returns bigint language plpgsql security definer set search_path = '' as $$
declare a record; v_run public.runs; v_id bigint; v_bad int;
begin
  select * into a from ea_private.agent_or_human(p_run_id, 'propose_decision', 1::smallint, 'propose_decision');
  v_run := a.run;
  if ea_private.current_kind() <> 'agent' then perform ea_private.raise_denied('decisions are proposed by agents; humans review them'); end if;
  if not ea_private.can_see_subject(p_subject_type, p_subject_id) then perform ea_private.raise_denied('subject not visible to agent'); end if;
  if coalesce(array_length(p_evidence_ids, 1), 0) = 0 then perform ea_private.raise_denied('a decision must cite at least one evidence row'); end if;
  select count(*) into v_bad from unnest(p_evidence_ids) x(id)
  where not exists (select 1 from public.evidence e where e.id = x.id and e.superseded_by is null
                    and ea_private.can_see_subject(e.subject_type, e.subject_id));
  if v_bad > 0 then perform ea_private.raise_denied(format('%s cited evidence ids are missing, superseded or not visible', v_bad)); end if;
  insert into public.decisions (run_id, made_by, loop, action, subject_type, subject_id, rationale, payload, autonomy_level)
  values (p_run_id, auth.uid(), v_run."loop", p_action, p_subject_type, p_subject_id, p_rationale, coalesce(p_payload, '{}'::jsonb), a.level)
  returning id into v_id;
  insert into public.decision_evidence (decision_id, evidence_id) select v_id, unnest(p_evidence_ids);
  return v_id;
end $$;

-- Checks that the decision was made in this run, for this action and subject.
create or replace function ea_private.require_decision(p_run public.runs, p_decision_id bigint, p_action text,
  p_subject_type text, p_subject_id text) returns public.decisions
language plpgsql stable security definer set search_path = '' as $$
declare d public.decisions;
begin
  select * into d from public.decisions where id = p_decision_id;
  if d.id is null or d.run_id is distinct from p_run.id then perform ea_private.raise_denied('decision not from this run'); end if;
  if d.action <> p_action then perform ea_private.raise_denied(format('decision action is %s, not %s', d.action, p_action)); end if;
  if d.subject_type <> p_subject_type or d.subject_id <> p_subject_id then perform ea_private.raise_denied('decision is about a different subject'); end if;
  if d.status <> 'proposed' then perform ea_private.raise_denied('decision already used'); end if;
  return d;
end $$;

create or replace function public.propose_strategy(p_run_id bigint, p_decision_id bigint, p_subject_type text,
  p_subject_id text, p_plan jsonb)
returns bigint language plpgsql security definer set search_path = '' as $$
declare a record; v_run public.runs; d public.decisions; v_version int; v_id bigint; v_status text := 'proposed'; v_uncited int;
begin
  select * into a from ea_private.agent_or_human(p_run_id, 'propose_strategy', 1::smallint, 'propose_strategy');
  v_run := a.run;
  if ea_private.current_kind() <> 'agent' then perform ea_private.raise_denied('strategies are proposed by agents'); end if;
  d := ea_private.require_decision(v_run, p_decision_id, 'propose_strategy', p_subject_type, p_subject_id);
  -- "No id, no claim": every evidence id the plan mentions must be cited by the decision.
  select count(*) into v_uncited
  from jsonb_path_query(p_plan, 'strict $.**.evidence[*]') x
  where not exists (select 1 from public.decision_evidence de
                    where de.decision_id = p_decision_id and de.evidence_id = (x #>> '{}')::bigint);
  if v_uncited > 0 then perform ea_private.raise_denied(format('plan cites %s evidence ids the decision does not', v_uncited)); end if;
  if ea_private.in_holdout(v_run."loop", p_subject_type, p_subject_id) then v_status := 'holdout'; end if;
  perform pg_advisory_xact_lock(hashtext(p_subject_type || ':' || p_subject_id));
  select coalesce(max(version), 0) + 1 into v_version from public.strategies
  where subject_type = p_subject_type and subject_id = p_subject_id;
  insert into public.strategies (subject_type, subject_id, version, plan, status, decision_id, proposed_by)
  values (p_subject_type, p_subject_id, v_version, p_plan, v_status, p_decision_id, auth.uid())
  returning id into v_id;
  update public.decisions set status = case when v_status = 'holdout' then 'superseded' else 'queued' end where id = p_decision_id;
  return v_id;
end $$;

-- Applies a field update for an approved decision. Called by apply_field_update (level 3+)
-- and by review_decision (level 2 path, after a human approves).
create or replace function ea_private.execute_field_update(p_decision public.decisions, p_value jsonb)
returns void language plpgsql security definer set search_path = '' as $$
declare
  t text := p_decision.payload->>'table';
  f text := p_decision.payload->>'field';
  v_id bigint := (p_decision.payload->>'row_id')::bigint;
  n int;
begin
  if not exists (select 1 from public.field_update_allowlist w where w.table_name = t and w.field = f) then
    perform ea_private.raise_denied(format('%s.%s is not on the field update allowlist', t, f));
  end if;
  update public.decisions set status = 'applying' where id = p_decision.id;
  perform set_config('ea.decision_id', p_decision.id::text, true);
  perform set_config('ea.run_id', coalesce(p_decision.run_id::text, ''), true);
  execute format('update public.%I set %I = (jsonb_populate_record(null::public.%I, $1)).%I where id = $2', t, f, t, f)
    using jsonb_build_object(f, p_value), v_id;
  get diagnostics n = row_count;
  if n <> 1 then perform ea_private.raise_denied('target row not found'); end if;
  perform set_config('ea.decision_id', '', true);
  perform set_config('ea.run_id', '', true);
  update public.decisions set status = 'applied' where id = p_decision.id;
end $$;

create or replace function public.apply_field_update(p_run_id bigint, p_decision_id bigint, p_table text,
  p_row_id bigint, p_field text, p_value jsonb)
returns text language plpgsql security definer set search_path = '' as $$
declare a record; v_run public.runs; d public.decisions; v_min smallint; v_territory bigint; v_subject_type text;
begin
  select * into a from ea_private.agent_or_human(p_run_id, 'apply_field_update', 2::smallint, 'apply_field_update');
  v_run := a.run;
  if ea_private.current_kind() <> 'agent' then perform ea_private.raise_denied('humans edit records directly'); end if;
  v_subject_type := case p_table when 'deals' then 'deal' when 'contacts' then 'contact' when 'companies' then 'company' end;
  if v_subject_type is null then perform ea_private.raise_denied('table not supported'); end if;
  d := ea_private.require_decision(v_run, p_decision_id, 'update_field', v_subject_type, p_row_id::text);
  if d.payload->>'table' is distinct from p_table or d.payload->>'field' is distinct from p_field
     or (d.payload->'value') is distinct from p_value then
    perform ea_private.raise_denied('decision payload does not match this update');
  end if;
  select w.min_level into v_min from public.field_update_allowlist w where w.table_name = p_table and w.field = p_field;
  if v_min is null then perform ea_private.raise_denied(format('%s.%s is not on the field update allowlist', p_table, p_field)); end if;
  if not ea_private.can_see_subject(v_subject_type, p_row_id::text) then perform ea_private.raise_denied('record outside agent scope'); end if;
  if not exists (select 1 from public.decision_evidence de join public.evidence e on e.id = de.evidence_id
                 where de.decision_id = d.id and e.strength = 'strong' and e.superseded_by is null) then
    perform ea_private.raise_denied('ledger changes need a decision that cites strong evidence');
  end if;
  if a.level >= v_min then
    perform ea_private.execute_field_update(d, p_value);
    return 'applied';
  end if;
  update public.decisions set status = 'queued' where id = d.id;
  return 'queued';
end $$;

-- Policy checks for an outbound touch. Returns null when allowed, else the reason.
create or replace function ea_private.touch_block_reason(p_loop text, p_contact_id bigint, p_channel text, p_sender_type text)
returns text language plpgsql stable security definer set search_path = '' as $$
declare v_company bigint; p record; v_n int;
begin
  select company_id into v_company from public.contacts where id = p_contact_id;
  if exists (select 1 from public.do_not_contact where contact_id = p_contact_id) then
    return 'contact is on the do-not-contact list';
  end if;
  if ea_private.in_holdout(p_loop, 'company', v_company::text) then
    return 'account is in a running experiment holdout for this loop';
  end if;
  for p in select * from public.policies where active loop
    if p.rule_type = 'max_touches' then
      select count(*) into v_n from public.touches t
      where t.contact_id = p_contact_id and t.status in ('scheduled','sent','pending_approval')
        and t.created_at > now() - make_interval(days => coalesce((p.params->>'window_days')::int, 14));
      if v_n >= coalesce((p.params->>'per_contact')::int, 3) then return format('policy "%s"', p.name); end if;
    elsif p.rule_type = 'partner_route' and p_sender_type <> 'partner' then
      if exists (select 1 from public.deal_partners dp join public.deals d on d.id = dp.deal_id
                 where d.company_id = v_company and d.archived_at is null
                   and dp.credit in (select jsonb_array_elements_text(p.params->'credit'))) then
        return format('policy "%s"', p.name);
      end if;
    elsif p.rule_type = 'blocked_channel' then
      if p.params->'channels' ? p_channel and p.params->'sender_types' ? p_sender_type then
        return format('policy "%s"', p.name);
      end if;
    end if;
  end loop;
  return null;
end $$;

create or replace function public.schedule_touch(p_run_id bigint, p_decision_id bigint, p_contact_id bigint,
  p_channel text, p_sender_type text, p_purpose text, p_content_ref text default null, p_scheduled_for timestamptz default null)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare a record; v_run public.runs; d public.decisions; v_reason text; v_status text; v_id bigint;
begin
  select * into a from ea_private.agent_or_human(p_run_id, 'schedule_touch', 2::smallint, 'schedule_touch');
  v_run := a.run;
  if ea_private.current_kind() <> 'agent' then perform ea_private.raise_denied('humans schedule touches in their own tools'); end if;
  if not ea_private.can_see_contact(p_contact_id) then perform ea_private.raise_denied('contact outside agent scope'); end if;
  d := ea_private.require_decision(v_run, p_decision_id, 'schedule_touch', 'contact', p_contact_id::text);
  v_reason := ea_private.touch_block_reason(v_run."loop", p_contact_id, p_channel, p_sender_type);
  v_status := case when v_reason is not null then 'blocked' when a.level >= 3 then 'scheduled' else 'pending_approval' end;
  insert into public.touches (decision_id, run_id, contact_id, channel, sender_type, purpose, content_ref, scheduled_for, status, blocked_reason)
  values (d.id, p_run_id, p_contact_id, p_channel, p_sender_type, p_purpose, p_content_ref, p_scheduled_for, v_status, v_reason)
  returning id into v_id;
  update public.decisions set status = case v_status when 'blocked' then 'rejected' when 'scheduled' then 'applied' else 'queued' end
  where id = d.id;
  return jsonb_build_object('touch_id', v_id, 'status', v_status, 'blocked_reason', v_reason);
end $$;

create or replace function public.create_commitment(p_run_id bigint, p_subject_type text, p_subject_id text,
  p_promise text, p_due_on date, p_evidence_id bigint)
returns bigint language plpgsql security definer set search_path = '' as $$
declare a record; v_run public.runs; v_owner uuid; v_id bigint;
begin
  select * into a from ea_private.agent_or_human(p_run_id, 'create_commitment', 1::smallint, 'create_commitment');
  v_run := a.run;
  if not ea_private.can_see_subject(p_subject_type, p_subject_id) then perform ea_private.raise_denied('subject not visible'); end if;
  if not exists (select 1 from public.evidence e where e.id = p_evidence_id and e.subject_type = p_subject_type
                 and e.subject_id = p_subject_id) then
    perform ea_private.raise_denied('a commitment must point to evidence about the same subject');
  end if;
  if p_subject_type = 'company' and p_subject_id ~ '^[0-9]+$' then
    select s.user_id into v_owner from public.companies c join public.sales s on s.id = c.sales_id where c.id = p_subject_id::bigint;
  end if;
  insert into public.commitments (subject_type, subject_id, promise, owner_user_id, due_on, source_evidence_id)
  values (p_subject_type, p_subject_id, p_promise, coalesce(v_owner, auth.uid()), p_due_on, p_evidence_id)
  returning id into v_id;
  return v_id;
end $$;

create or replace function public.escalate(p_run_id bigint, p_subject_type text, p_subject_id text,
  p_to_user uuid, p_reason text)
returns bigint language plpgsql security definer set search_path = '' as $$
declare a record; v_run public.runs; v_id bigint;
begin
  select * into a from ea_private.agent_or_human(p_run_id, 'escalate', 0::smallint, 'escalate');
  v_run := a.run;
  if not exists (select 1 from public.principals p where p.user_id = p_to_user and p.kind = 'human' and p.active) then
    perform ea_private.raise_denied('escalations go to an active human principal');
  end if;
  insert into public.escalations (run_id, subject_type, subject_id, to_user, reason)
  values (p_run_id, p_subject_type, p_subject_id, p_to_user, p_reason) returning id into v_id;
  return v_id;
end $$;

-- Skills -------------------------------------------------------------------------------

create or replace function public.propose_skill_version(p_run_id bigint, p_decision_id bigint, p_name text, p_body text)
returns int language plpgsql security definer set search_path = '' as $$
declare a record; v_run public.runs; v_version int;
begin
  select * into a from ea_private.agent_or_human(p_run_id, 'propose_skill_version', 1::smallint, 'propose_skill_version');
  v_run := a.run;
  if ea_private.current_kind() = 'agent' then
    perform ea_private.require_decision(v_run, p_decision_id, 'propose_skill_version', 'skill', p_name);
  elsif ea_private.current_role_name() <> 'owner' then
    perform ea_private.raise_denied('only owners propose skill versions directly');
  end if;
  perform pg_advisory_xact_lock(hashtext('skill:' || p_name));
  select coalesce(max(version), 0) + 1 into v_version from public.skills where name = p_name;
  insert into public.skills (name, version, body, proposed_by, proposed_decision_id)
  values (p_name, v_version, p_body, auth.uid(), p_decision_id);
  if p_decision_id is not null then update public.decisions set status = 'queued' where id = p_decision_id; end if;
  return v_version;
end $$;

create or replace function public.approve_skill(p_name text, p_version int)
returns void language plpgsql security definer set search_path = '' as $$
begin
  if not (ea_private.is_human() and ea_private.current_role_name() = 'owner') then
    perform ea_private.raise_denied('only owners approve skills');
  end if;
  update public.skills set status = 'retired' where name = p_name and status = 'approved';
  update public.skills set status = 'approved', approved_by = auth.uid(), approved_at = now()
  where name = p_name and version = p_version and status = 'proposed';
  if not found then perform ea_private.raise_denied('no proposed version to approve'); end if;
end $$;

-- Human review -------------------------------------------------------------------------

create or replace function public.review_decision(p_decision_id bigint, p_outcome text,
  p_note text default null, p_edited_payload jsonb default null)
returns text language plpgsql security definer set search_path = '' as $$
declare d public.decisions; v_payload jsonb; v_owner bigint;
begin
  if not ea_private.is_human() then perform ea_private.raise_denied('only humans review decisions'); end if;
  if p_outcome not in ('accepted','edited','rejected') then perform ea_private.raise_denied('outcome must be accepted, edited or rejected'); end if;
  select * into d from public.decisions where id = p_decision_id for update;
  if d.id is null or not ea_private.can_see_subject(d.subject_type, d.subject_id) then
    perform ea_private.raise_denied('decision not found or not visible');
  end if;
  if d.review_outcome is not null then perform ea_private.raise_denied('decision already reviewed'); end if;
  if ea_private.current_role_name() = 'readonly' then perform ea_private.raise_denied('read-only users do not review'); end if;
  if p_outcome = 'edited' and p_edited_payload is null then perform ea_private.raise_denied('edited reviews include the edited payload'); end if;

  update public.decisions set review_outcome = p_outcome, review_note = p_note, edited_payload = p_edited_payload,
    reviewed_by = auth.uid(), reviewed_at = now()
  where id = d.id;
  select * into d from public.decisions where id = p_decision_id;

  if p_outcome = 'rejected' then
    update public.decisions set status = 'rejected' where id = d.id and status in ('proposed','queued');
    update public.strategies set status = 'rejected' where decision_id = d.id and status = 'proposed';
    update public.touches set status = 'cancelled' where decision_id = d.id and status = 'pending_approval';
    update public.skills set status = 'rejected' where proposed_decision_id = d.id and status = 'proposed';
    return 'rejected';
  end if;

  -- accepted or edited: carry out whatever was waiting on this review
  if d.action = 'update_field' and d.status = 'queued' then
    -- the reviewer must be allowed to edit the record themselves
    if d.payload->>'table' = 'deals' then
      select sales_id into v_owner from public.deals where id = (d.payload->>'row_id')::bigint;
    elsif d.payload->>'table' = 'contacts' then
      select sales_id into v_owner from public.contacts where id = (d.payload->>'row_id')::bigint;
    elsif d.payload->>'table' = 'companies' then
      select sales_id into v_owner from public.companies where id = (d.payload->>'row_id')::bigint;
    end if;
    if not ea_private.can_edit(v_owner) then perform ea_private.raise_denied('reviewer cannot edit this record'); end if;
    v_payload := case when p_outcome = 'edited' then p_edited_payload->'value' else d.payload->'value' end;
    perform ea_private.execute_field_update(d, v_payload);
    return 'applied';
  elsif d.action = 'schedule_touch' and d.status = 'queued' then
    update public.touches set status = 'scheduled',
      purpose = coalesce(p_edited_payload->>'purpose', purpose),
      content_ref = coalesce(p_edited_payload->>'content_ref', content_ref)
    where decision_id = d.id and status = 'pending_approval';
    update public.decisions set status = 'applied' where id = d.id;
    return 'scheduled';
  elsif d.action = 'propose_strategy' then
    update public.strategies set status = 'approved',
      plan = case when p_outcome = 'edited' then coalesce(p_edited_payload->'plan', plan) else plan end,
      approved_by = auth.uid()
    where decision_id = d.id and status = 'proposed';
    update public.decisions set status = 'approved' where id = d.id;
    return 'approved';
  else
    update public.decisions set status = 'approved' where id = d.id and status in ('proposed','queued');
    return 'approved';
  end if;
end $$;

create or replace function public.activate_strategy(p_strategy_id bigint)
returns void language plpgsql security definer set search_path = '' as $$
declare s public.strategies;
begin
  select * into s from public.strategies where id = p_strategy_id for update;
  if s.id is null or not ea_private.is_human() or not ea_private.can_see_subject(s.subject_type, s.subject_id)
     or ea_private.current_role_name() not in ('owner','manager','rep') then
    perform ea_private.raise_denied('strategy not found or caller cannot activate it');
  end if;
  if s.status = 'holdout' then perform ea_private.raise_denied('holdout strategies are recorded but never activated'); end if;
  if s.status <> 'approved' then perform ea_private.raise_denied('only approved strategies can be activated'); end if;
  update public.strategies set status = 'retired' where subject_type = s.subject_type and subject_id = s.subject_id and status = 'active';
  update public.strategies set status = 'active' where id = s.id;
end $$;

-- Execute grants: authenticated only, never anon ----------------------------------------

do $$
declare f record;
begin
  for f in
    select p.oid::regprocedure as sig from pg_proc p join pg_namespace n on n.oid = p.pronamespace
    where n.nspname = 'public' and p.proname in ('start_run','end_run','record_run_event','get_account_context',
      'search_evidence','get_policies','record_evidence','supersede_evidence','propose_decision','propose_strategy',
      'apply_field_update','schedule_touch','create_commitment','escalate','propose_skill_version','approve_skill',
      'review_decision','activate_strategy')
  loop
    execute format('revoke all on function %s from public, anon', f.sig);
    execute format('grant execute on function %s to authenticated, service_role', f.sig);
  end loop;
end $$;

revoke all on all functions in schema ea_private from public, anon;
grant execute on all functions in schema ea_private to authenticated, service_role;
