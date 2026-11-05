-- 0009 Console and Slack support
--
-- 1. Loop prompts become versioned, reviewed records, like skills. A Rev Ops owner edits a
--    prompt in the console as a new version and approves it. Every run records the version
--    it used. The files in agents/loops/*/prompt.md are the starting versions.
-- 2. Read-only insight views over the primitives, for the console and for anyone with SQL.
-- 3. Slack: a map from Slack users to people, and two service-role functions so a Slack app
--    can show someone their review queue and record their review, as them.

-- As in 0001-0008, new tables get only the grants stated here (see 0001 for why).
alter default privileges in schema public revoke all on tables from anon, authenticated;
alter default privileges in schema public revoke all on sequences from anon, authenticated;

-- 1. Loop prompts --------------------------------------------------------------------

create table public.loop_prompts (
  "loop" text not null,
  version int not null check (version > 0),
  body text not null check (length(body) between 20 and 20000),
  note text,
  status text not null default 'proposed' check (status in ('proposed','approved','retired','rejected')),
  proposed_by uuid not null,
  approved_by uuid,
  approved_at timestamptz,
  created_at timestamptz not null default now(),
  primary key ("loop", version)
);
create unique index loop_prompts_one_approved on public.loop_prompts ("loop") where status = 'approved';
alter table public.loop_prompts enable row level security;

-- People can read every prompt. An agent reads only its own loop's prompts.
create policy ea_loop_prompts_select on public.loop_prompts for select to authenticated
  using (ea_private.is_human()
         or "loop" = (select d."loop" from public.agent_definitions d where d.id = ea_private.current_agent_definition_id()));
grant select on public.loop_prompts to authenticated;
grant all on public.loop_prompts to service_role;
create trigger ea_audit after insert or update or delete on public.loop_prompts
  for each row execute function ea_private.audit();

create or replace function public.propose_prompt_version(p_loop text, p_body text, p_note text default null)
returns int language plpgsql security definer set search_path = '' as $$
declare v_version int;
begin
  if not (ea_private.is_human() and ea_private.current_role_name() = 'owner') then
    perform ea_private.raise_denied('only owners propose prompt versions');
  end if;
  if not exists (select 1 from public.agent_definitions d where d."loop" = p_loop) then
    perform ea_private.raise_denied('unknown loop');
  end if;
  perform pg_advisory_xact_lock(hashtext('prompt:' || p_loop));
  select coalesce(max(version), 0) + 1 into v_version from public.loop_prompts where "loop" = p_loop;
  insert into public.loop_prompts ("loop", version, body, note, proposed_by)
  values (p_loop, v_version, p_body, p_note, auth.uid());
  return v_version;
end $$;

create or replace function public.approve_prompt(p_loop text, p_version int)
returns void language plpgsql security definer set search_path = '' as $$
begin
  if not (ea_private.is_human() and ea_private.current_role_name() = 'owner') then
    perform ea_private.raise_denied('only owners approve prompts');
  end if;
  if not exists (select 1 from public.loop_prompts where "loop" = p_loop and version = p_version and status = 'proposed') then
    perform ea_private.raise_denied('no proposed version to approve');
  end if;
  update public.loop_prompts set status = 'retired' where "loop" = p_loop and status = 'approved';
  update public.loop_prompts set status = 'approved', approved_by = auth.uid(), approved_at = now()
  where "loop" = p_loop and version = p_version;
end $$;

create or replace function public.reject_prompt(p_loop text, p_version int)
returns void language plpgsql security definer set search_path = '' as $$
begin
  if not (ea_private.is_human() and ea_private.current_role_name() = 'owner') then
    perform ea_private.raise_denied('only owners reject prompts');
  end if;
  update public.loop_prompts set status = 'rejected' where "loop" = p_loop and version = p_version and status = 'proposed';
  if not found then perform ea_private.raise_denied('no proposed version to reject'); end if;
end $$;

-- The approved prompt for the calling agent's loop (or any loop, for a person).
create or replace function public.get_loop_prompt(p_loop text)
returns table (version int, body text) language sql stable security invoker set search_path = '' as $$
  select lp.version, lp.body from public.loop_prompts lp where lp."loop" = p_loop and lp.status = 'approved'
$$;

revoke execute on function public.propose_prompt_version(text, text, text), public.approve_prompt(text, int),
  public.reject_prompt(text, int), public.get_loop_prompt(text) from public, anon;
grant execute on function public.propose_prompt_version(text, text, text), public.approve_prompt(text, int),
  public.reject_prompt(text, int), public.get_loop_prompt(text) to authenticated, service_role;

-- 2. Insight views ------------------------------------------------------------------------
-- security_invoker: each person sees only the rows their own access allows.

create view public.insight_evidence_in_reviews with (security_invoker = on) as
select e.kind, e.strength,
       count(*) filter (where d.review_outcome = 'accepted') as in_accepted,
       count(*) filter (where d.review_outcome = 'edited')   as in_edited,
       count(*) filter (where d.review_outcome = 'rejected') as in_rejected
from public.decision_evidence de
join public.decisions d on d.id = de.decision_id
join public.evidence  e on e.id = de.evidence_id
where d.review_outcome is not null
group by e.kind, e.strength;

create view public.insight_overrides with (security_invoker = on) as
select d."loop", d.action,
       count(*) as reviewed,
       round(avg((d.review_outcome <> 'accepted')::int), 2) as override_rate,
       (array_agg(d.review_note order by d.reviewed_at desc) filter (where d.review_note is not null))[1:3] as recent_notes
from public.decisions d
where d.review_outcome is not null
group by d."loop", d.action;

create view public.insight_model_performance with (security_invoker = on) as
select r."loop", r.model, r.prompt_version,
       count(distinct r.id) as runs,
       count(d.id) as decisions,
       round(avg((d.review_outcome = 'accepted')::int) filter (where d.review_outcome is not null), 2) as accepted_as_is
from public.runs r
left join public.decisions d on d.run_id = r.id
group by r."loop", r.model, r.prompt_version;

grant select on public.insight_evidence_in_reviews, public.insight_overrides, public.insight_model_performance
  to authenticated, service_role;

-- 3. Slack ---------------------------------------------------------------------------------

create table public.slack_user_map (
  slack_user_id text primary key check (slack_user_id ~ '^[UW][A-Z0-9]+$'),
  user_id uuid not null unique,
  mapped_by uuid,
  mapped_at timestamptz not null default now()
);
alter table public.slack_user_map enable row level security;
create policy ea_slack_map_owner on public.slack_user_map for all to authenticated
  using (ea_private.current_role_name() = 'owner') with check (ea_private.current_role_name() = 'owner');
grant select, insert, update, delete on public.slack_user_map to authenticated;
grant all on public.slack_user_map to service_role;
create trigger ea_audit after insert or update or delete on public.slack_user_map
  for each row execute function ea_private.audit();

-- Act as the person a Slack user is mapped to, for the rest of this transaction. Every check
-- inside review_decision then runs exactly as if that person had clicked in the console.
create or replace function ea_private.act_as_slack_user(p_slack_user text) returns uuid
language plpgsql security definer set search_path = '' as $$
declare v_user uuid;
begin
  select m.user_id into v_user from public.slack_user_map m where m.slack_user_id = p_slack_user;
  if v_user is null then perform ea_private.raise_denied('this Slack user is not mapped to a person'); end if;
  perform set_config('request.jwt.claims', json_build_object('sub', v_user, 'role', 'authenticated')::text, true);
  if not ea_private.is_human() then perform ea_private.raise_denied('mapped user is not an active person'); end if;
  return v_user;
end $$;

-- What the signed-in person can review right now: undecided proposals on records they may
-- approve work on. The console's review inbox and the Slack digest both use this.
create or replace function public.review_queue()
returns table (decision_id bigint, "loop" text, action text, subject_type text, subject_id text,
               subject_name text, rationale text, autonomy_level smallint, made_at timestamptz)
language plpgsql stable security definer set search_path = '' as $$
begin
  if not ea_private.is_human() then perform ea_private.raise_denied('only people have a review queue'); end if;
  if ea_private.current_role_name() = 'readonly' then return; end if;
  return query
  select d.id, d."loop", d.action, d.subject_type, d.subject_id,
         coalesce((select c.name from public.companies c where d.subject_type = 'company' and c.id::text = d.subject_id),
                  (select dl.name from public.deals dl where d.subject_type = 'deal' and dl.id::text = d.subject_id),
                  (select concat_ws(' ', ct.first_name, ct.last_name) from public.contacts ct where d.subject_type = 'contact' and ct.id::text = d.subject_id),
                  (select pa.name from public.partners pa where d.subject_type = 'partner' and pa.id::text = d.subject_id),
                  d.subject_id),
         d.rationale, d.autonomy_level, d.made_at
  from public.decisions d
  where d.review_outcome is null and d.status in ('proposed','queued')
    and ea_private.can_review_subject(d.subject_type, d.subject_id)
  order by d.made_at;
end $$;
revoke execute on function public.review_queue() from public, anon;
grant execute on function public.review_queue() to authenticated, service_role;

-- The same queue for a Slack user, for their morning digest.
create or replace function public.slack_review_queue(p_slack_user text)
returns table (decision_id bigint, "loop" text, action text, subject_type text, subject_id text,
               subject_name text, rationale text, autonomy_level smallint, made_at timestamptz)
language plpgsql security definer set search_path = '' as $$
begin
  perform ea_private.act_as_slack_user(p_slack_user);
  return query select * from public.review_queue();
end $$;

create or replace function public.slack_review_decision(p_slack_user text, p_decision_id bigint, p_outcome text, p_note text default null)
returns text language plpgsql security definer set search_path = '' as $$
begin
  perform ea_private.act_as_slack_user(p_slack_user);
  if p_outcome = 'edited' then perform ea_private.raise_denied('edits are made in the console, not from Slack'); end if;
  return public.review_decision(p_decision_id, p_outcome, coalesce(p_note, 'Reviewed in Slack'), null);
end $$;

revoke execute on function public.slack_review_queue(text), public.slack_review_decision(text, bigint, text, text)
  from public, anon, authenticated;
grant execute on function public.slack_review_queue(text), public.slack_review_decision(text, bigint, text, text)
  to service_role;
revoke execute on function ea_private.act_as_slack_user(text) from public, anon, authenticated;

alter default privileges in schema public grant all on tables to anon, authenticated;
alter default privileges in schema public grant all on sequences to anon, authenticated;
