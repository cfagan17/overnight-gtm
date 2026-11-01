-- 0003 The new primitives
--
-- A human CRM stores state (stage = Negotiation, amount = 200000). These tables store
-- why the state is what it is, so an agent can reason from it and a human can check it.
--
--   evidence     one sourced observation, append-only
--   strategies   the plan for one account or partner, versioned
--   experiments  a play run against a holdout fixed before outcomes are known
--   decisions    a choice made by a person or an agent, citing evidence
--   policies     rules of engagement, checked before every outbound action
--   commitments  something promised to a customer
--
-- (Agents themselves are in agent_definitions, 0002. Runs and skills are in 0004.)
--
-- Subjects are (subject_type, subject_id text) so the same tables work in greenfield
-- mode (ids are Atomic bigints) and sidecar mode (ids are Salesforce or HubSpot ids).

-- Sidecar mode: a thin mirror of external records, holding only what visibility needs.
-- Greenfield installs leave it empty.
create table public.external_subjects (
  subject_type text not null,
  subject_id text not null,
  source_system text not null check (source_system in ('salesforce','hubspot','other')),
  display_name text,
  owner_sales_id bigint references public.sales(id),
  territory_id bigint references public.territories(id),
  synced_at timestamptz not null default now(),
  primary key (subject_type, subject_id)
);

create or replace function ea_private.can_see_subject(p_type text, p_id text) returns boolean
language plpgsql stable security definer set search_path = '' as $$
declare v_num bigint;
begin
  -- Org-wide subjects: skills and loops (operating design), territories (the carve is public
  -- inside the company), and partners (including candidates that are not partners yet).
  if p_type in ('skill','loop','territory','partner') then return ea_private.current_role_name() <> 'none'; end if;
  if p_id ~ '^[0-9]+$' then v_num := p_id::bigint; end if;
  if v_num is not null then
    if p_type = 'company' and exists (select 1 from public.companies where id = v_num) then
      return ea_private.can_see_company(v_num);
    elsif p_type = 'deal' and exists (select 1 from public.deals where id = v_num) then
      return ea_private.can_see_deal(v_num);
    elsif p_type = 'contact' and exists (select 1 from public.contacts where id = v_num) then
      return ea_private.can_see_contact(v_num);
    end if;
  end if;
  return coalesce((select ea_private.can_see(e.owner_sales_id, e.territory_id)
                   from public.external_subjects e
                   where e.subject_type = p_type and e.subject_id = p_id), false);
end $$;

-- Evidence ------------------------------------------------------------------------

-- Strength belongs to the kind of evidence, never to a model's self-assessment.
create table public.evidence_kinds (
  kind text primary key,
  strength text not null check (strength in ('strong','weak')),
  description text not null
);

insert into public.evidence_kinds (kind, strength, description) values
  ('call_quote',        'strong', 'Words the person said on a recorded call, with a timestamp'),
  ('email_from_contact','strong', 'An email sent by the person from their own address'),
  ('signature_block',   'strong', 'Name, title or company read from the person''s own email signature'),
  ('meeting_attended',  'strong', 'Calendar record of the person attending a meeting'),
  ('product_usage',     'strong', 'A metric from the product''s own telemetry'),
  ('crm_record',        'strong', 'A fact already in the ledger (contract, closed deal)'),
  ('rep_observation',   'strong', 'Something a seller saw or heard first-hand and wrote down'),
  ('partner_report',    'weak',   'Something a partner told us about the account'),
  ('enrichment_vendor', 'weak',   'A field from a data vendor'),
  ('web_page',          'weak',   'A public web page about the account or person'),
  ('social_post',       'weak',   'A public social post'),
  ('inferred',          'weak',   'A conclusion drawn from other evidence, not observed');

create table public.evidence (
  id bigint generated always as identity primary key,
  subject_type text not null check (subject_type in ('company','contact','deal','partner','territory')),
  subject_id text not null,
  kind text not null references public.evidence_kinds(kind),
  claim text not null check (length(claim) between 3 and 2000),
  source_uri text not null check (length(source_uri) > 0),
  observed_at timestamptz not null,
  strength text not null,
  recorded_by uuid not null,
  run_id bigint,                                -- set when an agent recorded it
  superseded_by bigint references public.evidence(id),
  created_at timestamptz not null default now()
);
create index evidence_subject_idx on public.evidence (subject_type, subject_id, observed_at desc);

create or replace function ea_private.evidence_guard() returns trigger
language plpgsql set search_path = '' as $$
begin
  if tg_op = 'INSERT' then
    select k.strength into new.strength from public.evidence_kinds k where k.kind = new.kind;
    new.recorded_by := coalesce(auth.uid(), new.recorded_by);
    return new;
  end if;
  -- UPDATE: evidence is append-only. The only allowed change is marking it superseded once.
  if old.superseded_by is null and new.superseded_by is not null
     and (to_jsonb(new) - 'superseded_by') = (to_jsonb(old) - 'superseded_by') then
    return new;
  end if;
  raise exception 'ea: evidence is append-only (only superseded_by may be set, once)' using errcode = '42501';
end $$;
create trigger ea_evidence_guard before insert or update on public.evidence
  for each row execute function ea_private.evidence_guard();

-- Strategies -----------------------------------------------------------------------

create table public.strategies (
  id bigint generated always as identity primary key,
  subject_type text not null check (subject_type in ('company','partner','territory')),
  subject_id text not null,
  version int not null,
  plan jsonb not null,
  status text not null default 'proposed'
    check (status in ('proposed','approved','active','retired','rejected','holdout')),
  decision_id bigint,
  proposed_by uuid not null,
  approved_by uuid,
  created_at timestamptz not null default now(),
  unique (subject_type, subject_id, version)
);
create unique index strategies_one_active on public.strategies (subject_type, subject_id) where status = 'active';

-- Experiments ----------------------------------------------------------------------

create table public.experiments (
  id bigint generated always as identity primary key,
  name text not null,
  hypothesis text not null,
  loop text not null,
  metric text not null,                 -- e.g. meeting_booked_within_60d
  subject_type text not null,
  holdout_pct numeric not null check (holdout_pct > 0 and holdout_pct < 100),
  status text not null default 'draft' check (status in ('draft','running','closed')),
  starts_at date,
  ends_at date,
  created_by uuid not null default auth.uid()
);

create table public.experiment_assignments (
  experiment_id bigint not null references public.experiments(id),
  subject_id text not null,
  arm text not null check (arm in ('treatment','holdout')),
  assigned_at timestamptz not null default now(),
  primary key (experiment_id, subject_id)
);

create table public.experiment_outcomes (
  experiment_id bigint not null references public.experiments(id),
  subject_id text not null,
  metric_value numeric not null,
  observed_at timestamptz not null default now(),
  primary key (experiment_id, subject_id)
);

-- Decisions ------------------------------------------------------------------------

create table public.decisions (
  id bigint generated always as identity primary key,
  run_id bigint,
  made_by uuid not null,
  loop text not null,
  action text not null,                 -- e.g. propose_strategy, update_field, schedule_touch
  subject_type text not null,
  subject_id text not null,
  rationale text not null check (length(rationale) >= 10),
  payload jsonb not null default '{}'::jsonb,
  autonomy_level smallint not null check (autonomy_level between 0 and 4),
  status text not null default 'proposed'
    check (status in ('proposed','queued','approved','rejected','applying','applied','failed','superseded')),
  review_outcome text check (review_outcome in ('accepted','edited','rejected')),
  edited_payload jsonb,
  review_note text,
  reviewed_by uuid,
  reviewed_at timestamptz,
  made_at timestamptz not null default now()
);
create index decisions_loop_idx on public.decisions (loop, made_at desc);
create index decisions_subject_idx on public.decisions (subject_type, subject_id);

create table public.decision_evidence (
  decision_id bigint not null references public.decisions(id),
  evidence_id bigint not null references public.evidence(id),
  primary key (decision_id, evidence_id)
);

alter table public.strategies add constraint strategies_decision_fk foreign key (decision_id) references public.decisions(id);

-- Policies -------------------------------------------------------------------------

create table public.policies (
  id bigint generated always as identity primary key,
  name text not null unique,
  rule_type text not null check (rule_type in ('max_touches','do_not_contact','partner_route','blocked_channel')),
  params jsonb not null default '{}'::jsonb,
  active boolean not null default true
);

create table public.do_not_contact (
  contact_id bigint primary key references public.contacts(id) on delete cascade,
  reason text not null,
  added_by uuid not null default auth.uid(),
  added_at timestamptz not null default now()
);

insert into public.policies (name, rule_type, params) values
  ('Max 3 touches per contact in 14 days', 'max_touches', '{"per_contact": 3, "window_days": 14}'),
  ('Respect do-not-contact list', 'do_not_contact', '{}'),
  ('Partner-sourced accounts go through the partner', 'partner_route', '{"credit": ["sourced","resold"]}'),
  ('No agent-sent SMS', 'blocked_channel', '{"channels": ["sms"], "sender_types": ["agent"]}');

-- Commitments ------------------------------------------------------------------------

create table public.commitments (
  id bigint generated always as identity primary key,
  subject_type text not null default 'company',
  subject_id text not null,
  promise text not null,
  owner_user_id uuid not null,
  due_on date,
  status text not null default 'open' check (status in ('open','fulfilled','released')),
  source_evidence_id bigint references public.evidence(id),
  decision_id bigint references public.decisions(id),
  created_at timestamptz not null default now()
);

-- RLS: reads follow the subject; writes go through functions (0005) -------------------

alter table public.external_subjects enable row level security;
alter table public.evidence_kinds enable row level security;
alter table public.evidence enable row level security;
alter table public.strategies enable row level security;
alter table public.experiments enable row level security;
alter table public.experiment_assignments enable row level security;
alter table public.experiment_outcomes enable row level security;
alter table public.decisions enable row level security;
alter table public.decision_evidence enable row level security;
alter table public.policies enable row level security;
alter table public.do_not_contact enable row level security;
alter table public.commitments enable row level security;

create policy ea_external_select on public.external_subjects for select to authenticated
  using (ea_private.can_see(owner_sales_id, territory_id));
create policy ea_kinds_select on public.evidence_kinds for select to authenticated using (true);
create policy ea_evidence_select on public.evidence for select to authenticated
  using (ea_private.can_see_subject(subject_type, subject_id));
create policy ea_strategies_select on public.strategies for select to authenticated
  using (ea_private.can_see_subject(subject_type, subject_id));
create policy ea_experiments_select on public.experiments for select to authenticated
  using (ea_private.current_role_name() <> 'none');
create policy ea_experiments_write on public.experiments for all to authenticated
  using (ea_private.is_human() and ea_private.current_role_name() = 'owner')
  with check (ea_private.is_human() and ea_private.current_role_name() = 'owner');
-- Assignments are readable so loops can check the arm; nobody writes them directly.
create policy ea_assignments_select on public.experiment_assignments for select to authenticated
  using (ea_private.current_role_name() <> 'none');
create policy ea_outcomes_select on public.experiment_outcomes for select to authenticated
  using (ea_private.current_role_name() in ('owner','manager','readonly'));
create policy ea_decisions_select on public.decisions for select to authenticated
  using (made_by = auth.uid() or ea_private.can_see_subject(subject_type, subject_id));
create policy ea_decision_evidence_select on public.decision_evidence for select to authenticated
  using (exists (select 1 from public.decisions d where d.id = decision_id));
create policy ea_policies_select on public.policies for select to authenticated using (true);
create policy ea_policies_write on public.policies for all to authenticated
  using (ea_private.is_human() and ea_private.current_role_name() = 'owner')
  with check (ea_private.is_human() and ea_private.current_role_name() = 'owner');
create policy ea_dnc_select on public.do_not_contact for select to authenticated
  using (ea_private.can_see_contact(contact_id));
create policy ea_dnc_insert on public.do_not_contact for insert to authenticated
  with check (ea_private.is_human() and ea_private.can_see_contact(contact_id));
create policy ea_dnc_delete on public.do_not_contact for delete to authenticated
  using (ea_private.is_human() and ea_private.current_role_name() in ('owner','manager'));
create policy ea_commitments_select on public.commitments for select to authenticated
  using (ea_private.can_see_subject(subject_type, subject_id));
create policy ea_commitments_update on public.commitments for update to authenticated
  using (ea_private.is_human() and ea_private.can_see_subject(subject_type, subject_id))
  with check (ea_private.is_human() and ea_private.can_see_subject(subject_type, subject_id));

grant select on public.external_subjects, public.evidence_kinds, public.evidence, public.strategies,
  public.experiments, public.experiment_assignments, public.experiment_outcomes, public.decisions,
  public.decision_evidence, public.policies, public.do_not_contact, public.commitments to authenticated;
grant insert, update, delete on public.experiments, public.policies to authenticated;
grant insert, delete on public.do_not_contact to authenticated;
grant update (status) on public.commitments to authenticated;
grant all on all tables in schema public to service_role;
grant usage, select on all sequences in schema public to authenticated, service_role;

do $$
declare t text;
begin
  foreach t in array array['evidence','strategies','experiments','experiment_assignments','decisions',
                           'policies','commitments','do_not_contact','external_subjects']
  loop
    execute format('create trigger ea_audit after insert or update or delete on public.%I
                    for each row execute function ea_private.audit()', t);
  end loop;
end $$;
