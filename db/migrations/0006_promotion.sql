-- 0006 Learning and promotion
--
-- A loop moves up a level only when its record clears a bar. Two kinds of evidence:
--   * live review record: accepted / edited / rejected counts from decisions
--   * replay evals: scores on a fixed set of past cases, recorded per model and prompt
-- Plus holdout experiments, so a loop that acts on customers is measured against a
-- comparison group fixed before any outcome is known, never against last year.

-- Review statistics -----------------------------------------------------------------

create view public.loop_review_stats with (security_invoker = on) as
select r.agent_definition_id,
       d."loop",
       d.autonomy_level,
       count(*)                                                     as decisions,
       count(*) filter (where d.review_outcome is not null)         as reviewed,
       round(avg((d.review_outcome = 'accepted')::int) filter (where d.review_outcome is not null), 3) as accepted_as_is,
       round(avg((d.review_outcome = 'edited')::int)   filter (where d.review_outcome is not null), 3) as edited,
       round(avg((d.review_outcome = 'rejected')::int) filter (where d.review_outcome is not null), 3) as rejected
from public.decisions d
join public.runs r on r.id = d.run_id
where d.made_at > now() - interval '60 days'
group by r.agent_definition_id, d."loop", d.autonomy_level;
grant select on public.loop_review_stats to authenticated, service_role;

-- Replay evals -------------------------------------------------------------------------

create table public.replay_results (
  id bigint generated always as identity primary key,
  agent_definition_id bigint not null references public.agent_definitions(id),
  eval_set text not null,
  model text not null,
  prompt_version text not null,
  skill_versions jsonb not null default '{}'::jsonb,
  cases int not null check (cases > 0),
  score numeric not null check (score between 0 and 1),
  baseline_score numeric check (baseline_score between 0 and 1),   -- the version currently in production
  recorded_by uuid not null default auth.uid(),
  run_at timestamptz not null default now()
);

-- Policy violations: a human confirms an agent action broke a rule. One violation demotes.
create table public.policy_violations (
  id bigint generated always as identity primary key,
  decision_id bigint not null references public.decisions(id),
  agent_definition_id bigint not null references public.agent_definitions(id),
  note text not null,
  flagged_by uuid not null default auth.uid(),
  flagged_at timestamptz not null default now()
);

create table public.autonomy_changes (
  id bigint generated always as identity primary key,
  agent_definition_id bigint not null references public.agent_definitions(id),
  from_level smallint not null,
  to_level smallint not null,
  reason text not null,
  checks jsonb not null,
  decided_by uuid,
  decided_at timestamptz not null default now()
);

-- Bars for moving up. Starting guesses; set them from your own data.
create table public.promotion_rules (
  to_level smallint primary key check (to_level between 1 and 4),
  min_reviewed int not null,
  min_accepted_as_is numeric not null,
  max_rejected numeric not null,
  needs_replay_at_least_baseline boolean not null default true,
  needs_zero_violations boolean not null default true,
  needs_audit_better_than_human boolean not null default false
);
insert into public.promotion_rules values
  (1,   0, 0.00, 1.00, true,  true, false),
  (2, 100, 0.80, 0.10, true,  true, false),
  (3, 200, 0.95, 0.03, true,  true, false),
  (4, 200, 0.95, 0.03, true,  true, true);

-- Sampled audits for level 4: the same work checked for agent and for humans.
create table public.audit_samples (
  id bigint generated always as identity primary key,
  loop text not null,
  sample_of text not null check (sample_of in ('agent','human')),
  items int not null check (items > 0),
  errors int not null check (errors >= 0),
  audited_by uuid not null default auth.uid(),
  audited_at timestamptz not null default now(),
  check (errors <= items)
);

alter table public.replay_results enable row level security;
alter table public.policy_violations enable row level security;
alter table public.autonomy_changes enable row level security;
alter table public.promotion_rules enable row level security;
alter table public.audit_samples enable row level security;
create policy ea_replay_select on public.replay_results for select to authenticated using (ea_private.current_role_name() <> 'none');
create policy ea_violations_select on public.policy_violations for select to authenticated using (ea_private.current_role_name() <> 'none');
create policy ea_autonomy_select on public.autonomy_changes for select to authenticated using (ea_private.current_role_name() <> 'none');
create policy ea_rules_select on public.promotion_rules for select to authenticated using (true);
create policy ea_rules_write on public.promotion_rules for all to authenticated
  using (ea_private.is_human() and ea_private.current_role_name() = 'owner')
  with check (ea_private.is_human() and ea_private.current_role_name() = 'owner');
create policy ea_audit_samples_select on public.audit_samples for select to authenticated using (ea_private.current_role_name() <> 'none');
create policy ea_audit_samples_insert on public.audit_samples for insert to authenticated
  with check (ea_private.is_human() and ea_private.current_role_name() in ('owner','manager'));
grant select on public.replay_results, public.policy_violations, public.autonomy_changes, public.promotion_rules,
  public.audit_samples to authenticated;
grant insert, update on public.promotion_rules to authenticated;
grant insert on public.audit_samples to authenticated;
grant all on public.replay_results, public.policy_violations, public.autonomy_changes, public.promotion_rules,
  public.audit_samples to service_role;
grant usage, select on all sequences in schema public to authenticated, service_role;

create or replace function public.record_replay_result(p_agent_definition_id bigint, p_eval_set text, p_model text,
  p_prompt_version text, p_skill_versions jsonb, p_cases int, p_score numeric, p_baseline numeric)
returns bigint language plpgsql security definer set search_path = '' as $$
declare v_id bigint;
begin
  if not ((ea_private.is_human() and ea_private.current_role_name() = 'owner') or auth.role() = 'service_role') then
    perform ea_private.raise_denied('replay results are recorded by owners or the eval service');
  end if;
  insert into public.replay_results (agent_definition_id, eval_set, model, prompt_version, skill_versions, cases, score, baseline_score)
  values (p_agent_definition_id, p_eval_set, p_model, p_prompt_version, coalesce(p_skill_versions, '{}'::jsonb), p_cases, p_score, p_baseline)
  returning id into v_id;
  return v_id;
end $$;

-- What a promotion to p_to_level would need, and whether the loop meets it today.
create or replace function public.promotion_check(p_agent_definition_id bigint, p_to_level smallint)
returns jsonb language plpgsql stable security definer set search_path = '' as $$
declare
  def public.agent_definitions; rule public.promotion_rules;
  v_reviewed int; v_acc numeric; v_rej numeric; v_viol int; v_replay public.replay_results;
  v_agent_err numeric; v_human_err numeric; checks jsonb := '[]'::jsonb; ok boolean := true;
begin
  if ea_private.current_role_name() = 'none' then perform ea_private.raise_denied('not a principal'); end if;
  select * into def from public.agent_definitions where id = p_agent_definition_id;
  select * into rule from public.promotion_rules where to_level = p_to_level;
  if def.id is null or rule.to_level is null then perform ea_private.raise_denied('unknown agent or level'); end if;

  select count(*) filter (where d.review_outcome is not null),
         avg((d.review_outcome = 'accepted')::int) filter (where d.review_outcome is not null),
         avg((d.review_outcome = 'rejected')::int) filter (where d.review_outcome is not null)
    into v_reviewed, v_acc, v_rej
  from public.decisions d join public.runs r on r.id = d.run_id
  where r.agent_definition_id = def.id and d.autonomy_level = def.autonomy_level
    and d.made_at > now() - interval '60 days';

  select count(*) into v_viol from public.policy_violations v
  where v.agent_definition_id = def.id and v.flagged_at > now() - interval '60 days';

  select * into v_replay from public.replay_results rr where rr.agent_definition_id = def.id
  order by rr.run_at desc limit 1;

  checks := checks || jsonb_build_object('check', 'within max_autonomy', 'need', def.max_autonomy, 'have', p_to_level,
                                         'pass', p_to_level <= def.max_autonomy);
  ok := ok and p_to_level <= def.max_autonomy;
  checks := checks || jsonb_build_object('check', 'one level at a time', 'need', def.autonomy_level + 1, 'have', p_to_level,
                                         'pass', p_to_level = def.autonomy_level + 1);
  ok := ok and p_to_level = def.autonomy_level + 1;
  checks := checks || jsonb_build_object('check', 'reviewed decisions', 'need', rule.min_reviewed, 'have', coalesce(v_reviewed, 0),
                                         'pass', coalesce(v_reviewed, 0) >= rule.min_reviewed);
  ok := ok and coalesce(v_reviewed, 0) >= rule.min_reviewed;
  if rule.min_reviewed > 0 then
    checks := checks || jsonb_build_object('check', 'accepted as is', 'need', rule.min_accepted_as_is, 'have', round(coalesce(v_acc, 0), 3),
                                           'pass', coalesce(v_acc, 0) >= rule.min_accepted_as_is);
    ok := ok and coalesce(v_acc, 0) >= rule.min_accepted_as_is;
    checks := checks || jsonb_build_object('check', 'rejected', 'need_at_most', rule.max_rejected, 'have', round(coalesce(v_rej, 1), 3),
                                           'pass', coalesce(v_rej, 1) <= rule.max_rejected);
    ok := ok and coalesce(v_rej, 1) <= rule.max_rejected;
  end if;
  if rule.needs_zero_violations then
    checks := checks || jsonb_build_object('check', 'policy violations in 60 days', 'need_at_most', 0, 'have', v_viol, 'pass', v_viol = 0);
    ok := ok and v_viol = 0;
  end if;
  if rule.needs_replay_at_least_baseline then
    checks := checks || jsonb_build_object('check', 'latest replay at least baseline',
      'have', case when v_replay.id is null then null else jsonb_build_object('score', v_replay.score, 'baseline', v_replay.baseline_score,
              'model', v_replay.model, 'prompt_version', v_replay.prompt_version) end,
      'pass', v_replay.id is not null and v_replay.score >= coalesce(v_replay.baseline_score, 0));
    ok := ok and v_replay.id is not null and v_replay.score >= coalesce(v_replay.baseline_score, 0);
  end if;
  if rule.needs_audit_better_than_human then
    select sum(errors)::numeric / nullif(sum(items), 0) into v_agent_err from public.audit_samples
      where loop = def."loop" and sample_of = 'agent' and audited_at > now() - interval '60 days';
    select sum(errors)::numeric / nullif(sum(items), 0) into v_human_err from public.audit_samples
      where loop = def."loop" and sample_of = 'human' and audited_at > now() - interval '60 days';
    checks := checks || jsonb_build_object('check', 'audited error rate below human rate',
      'have', jsonb_build_object('agent', round(v_agent_err, 3), 'human', round(v_human_err, 3)),
      'pass', v_agent_err is not null and v_human_err is not null and v_agent_err < v_human_err);
    ok := ok and v_agent_err is not null and v_human_err is not null and v_agent_err < v_human_err;
  end if;
  return jsonb_build_object('agent', def.name, 'loop', def."loop", 'from_level', def.autonomy_level,
                            'to_level', p_to_level, 'eligible', ok, 'checks', checks);
end $$;

-- Owners decide promotions. Moving up requires the check to pass; there is no override.
-- Moving down is always allowed.
create or replace function public.decide_promotion(p_agent_definition_id bigint, p_to_level smallint, p_reason text)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare def public.agent_definitions; v_check jsonb;
begin
  if not (ea_private.is_human() and ea_private.current_role_name() = 'owner') then
    perform ea_private.raise_denied('only owners change autonomy levels');
  end if;
  select * into def from public.agent_definitions where id = p_agent_definition_id for update;
  if p_to_level > def.autonomy_level then
    v_check := public.promotion_check(p_agent_definition_id, p_to_level);
    if not (v_check->>'eligible')::boolean then
      perform ea_private.raise_denied('promotion check failed: ' || (v_check->'checks')::text);
    end if;
  else
    v_check := jsonb_build_object('demotion', true);
  end if;
  perform set_config('ea.promotion_in_progress', 'on', true);
  update public.agent_definitions set autonomy_level = p_to_level where id = def.id;
  perform set_config('ea.promotion_in_progress', '', true);
  insert into public.autonomy_changes (agent_definition_id, from_level, to_level, reason, checks, decided_by)
  values (def.id, def.autonomy_level, p_to_level, p_reason, v_check, auth.uid());
  return v_check;
end $$;

-- A confirmed violation demotes the loop one level immediately.
create or replace function public.flag_policy_violation(p_decision_id bigint, p_note text)
returns smallint language plpgsql security definer set search_path = '' as $$
declare d public.decisions; def public.agent_definitions; v_new smallint;
begin
  if not (ea_private.is_human() and ea_private.current_role_name() in ('owner','manager')) then
    perform ea_private.raise_denied('only owners and managers flag violations');
  end if;
  select * into d from public.decisions where id = p_decision_id;
  select ad.* into def from public.runs r join public.agent_definitions ad on ad.id = r.agent_definition_id where r.id = d.run_id;
  if def.id is null then perform ea_private.raise_denied('decision has no agent run'); end if;
  insert into public.policy_violations (decision_id, agent_definition_id, note) values (d.id, def.id, p_note);
  v_new := greatest(def.autonomy_level - 1, 0);
  perform set_config('ea.promotion_in_progress', 'on', true);
  update public.agent_definitions set autonomy_level = v_new where id = def.id;
  perform set_config('ea.promotion_in_progress', '', true);
  insert into public.autonomy_changes (agent_definition_id, from_level, to_level, reason, checks, decided_by)
  values (def.id, def.autonomy_level, v_new, 'policy violation: ' || p_note, jsonb_build_object('decision_id', d.id), auth.uid());
  return v_new;
end $$;

-- Experiments ------------------------------------------------------------------------

-- Deterministic assignment: the arm depends only on the experiment and subject ids, so
-- it can be recomputed and audited, and nobody chooses which accounts get the treatment.
create or replace function public.assign_experiment(p_experiment_id bigint, p_subject_ids text[])
returns jsonb language plpgsql security definer set search_path = '' as $$
declare e public.experiments; v_t int; v_h int;
begin
  if not (ea_private.is_human() and ea_private.current_role_name() = 'owner') then
    perform ea_private.raise_denied('only owners assign experiments');
  end if;
  select * into e from public.experiments where id = p_experiment_id for update;
  if e.status <> 'draft' then perform ea_private.raise_denied('assignments are fixed once an experiment starts'); end if;
  insert into public.experiment_assignments (experiment_id, subject_id, arm)
  select e.id, s,
         case when (('x' || substr(md5(e.id::text || ':' || s), 1, 8))::bit(32)::bigint % 10000) < (e.holdout_pct * 100)
              then 'holdout' else 'treatment' end
  from unnest(p_subject_ids) s
  on conflict do nothing;
  select count(*) filter (where arm = 'treatment'), count(*) filter (where arm = 'holdout') into v_t, v_h
  from public.experiment_assignments where experiment_id = e.id;
  return jsonb_build_object('treatment', v_t, 'holdout', v_h);
end $$;

create or replace function public.start_experiment(p_experiment_id bigint)
returns void language plpgsql security definer set search_path = '' as $$
begin
  if not (ea_private.is_human() and ea_private.current_role_name() = 'owner') then
    perform ea_private.raise_denied('only owners start experiments');
  end if;
  update public.experiments set status = 'running', starts_at = current_date
  where id = p_experiment_id and status = 'draft'
    and exists (select 1 from public.experiment_assignments a where a.experiment_id = p_experiment_id and a.arm = 'holdout');
  if not found then perform ea_private.raise_denied('experiment must be a draft with at least one holdout subject'); end if;
end $$;

create or replace function public.record_experiment_outcome(p_experiment_id bigint, p_subject_id text, p_value numeric)
returns void language plpgsql security definer set search_path = '' as $$
begin
  if not ((ea_private.is_human() and ea_private.current_role_name() in ('owner','manager')) or auth.role() = 'service_role') then
    perform ea_private.raise_denied('outcomes are recorded by owners, managers or the analytics service');
  end if;
  if not exists (select 1 from public.experiment_assignments where experiment_id = p_experiment_id and subject_id = p_subject_id) then
    perform ea_private.raise_denied('subject is not in this experiment');
  end if;
  insert into public.experiment_outcomes (experiment_id, subject_id, metric_value) values (p_experiment_id, p_subject_id, p_value)
  on conflict (experiment_id, subject_id) do update set metric_value = excluded.metric_value, observed_at = now();
end $$;

-- Difference between arms with a 95% range. For 0/1 outcomes this is the two-proportion
-- standard error from the design doc; subjects with no recorded outcome count as 0.
create or replace function public.experiment_result(p_experiment_id bigint)
returns jsonb language plpgsql stable security definer set search_path = '' as $$
declare n1 int; n2 int; m1 numeric; m2 numeric; v1 numeric; v2 numeric; se numeric; diff numeric; need numeric;
begin
  if ea_private.current_role_name() not in ('owner','manager','readonly') then perform ea_private.raise_denied('not allowed'); end if;
  select count(*), avg(coalesce(o.metric_value, 0)), var_samp(coalesce(o.metric_value, 0)) into n1, m1, v1
  from public.experiment_assignments a left join public.experiment_outcomes o using (experiment_id, subject_id)
  where a.experiment_id = p_experiment_id and a.arm = 'treatment';
  select count(*), avg(coalesce(o.metric_value, 0)), var_samp(coalesce(o.metric_value, 0)) into n2, m2, v2
  from public.experiment_assignments a left join public.experiment_outcomes o using (experiment_id, subject_id)
  where a.experiment_id = p_experiment_id and a.arm = 'holdout';
  if n1 < 2 or n2 < 2 then return jsonb_build_object('error', 'need at least 2 subjects per arm'); end if;
  diff := m1 - m2;
  se := sqrt(coalesce(v1, 0) / n1 + coalesce(v2, 0) / n2);
  -- accounts per arm needed to detect this difference with 80% power at 5% significance
  need := case when diff = 0 then null else ceil(7.84 * (coalesce(v1, 0) + coalesce(v2, 0)) / (diff * diff)) end;
  return jsonb_build_object(
    'treatment', jsonb_build_object('n', n1, 'mean', round(m1, 4)),
    'holdout', jsonb_build_object('n', n2, 'mean', round(m2, 4)),
    'difference', round(diff, 4),
    'standard_error', round(se, 4),
    'range_95', jsonb_build_array(round(diff - 1.96 * se, 4), round(diff + 1.96 * se, 4)),
    'conclusive', (diff - 1.96 * se) > 0 or (diff + 1.96 * se) < 0,
    'subjects_per_arm_needed_for_this_difference', need);
end $$;

do $$
declare f record;
begin
  for f in
    select p.oid::regprocedure as sig from pg_proc p join pg_namespace n on n.oid = p.pronamespace
    where n.nspname = 'public' and p.proname in ('record_replay_result','promotion_check','decide_promotion',
      'flag_policy_violation','assign_experiment','start_experiment','record_experiment_outcome','experiment_result')
  loop
    execute format('revoke all on function %s from public, anon', f.sig);
    execute format('grant execute on function %s to authenticated, service_role', f.sig);
  end loop;
end $$;

create trigger ea_audit after insert or update or delete on public.promotion_rules
  for each row execute function ea_private.audit();
