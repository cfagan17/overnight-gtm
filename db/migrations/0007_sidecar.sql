-- 0007 Sidecar mode: the same primitives and loops beside Salesforce or HubSpot
--
-- In sidecar mode the ledger stays in the existing CRM. Supabase holds the new
-- primitives (evidence, strategies, decisions, runs, skills, policies, commitments) plus
-- a thin mirror of record ids, owners and territories (external_subjects, 0003) so
-- visibility rules work the same way. Agent changes to the CRM go out through one door:
-- outbound_changes, sent by a writeback worker as one integration user, each change
-- tagged with the decision that caused it. Customer data is not copied wholesale.

create table public.sidecar_user_map (
  source_system text not null check (source_system in ('salesforce','hubspot')),
  external_user_id text not null,
  sales_id bigint not null references public.sales(id),
  primary key (source_system, external_user_id)
);

create table public.sidecar_territory_map (
  source_system text not null check (source_system in ('salesforce','hubspot')),
  external_key text not null,                    -- e.g. a Salesforce territory name or a region code
  territory_id bigint not null references public.territories(id),
  primary key (source_system, external_key)
);

create table public.external_field_allowlist (
  source_system text not null check (source_system in ('salesforce','hubspot')),
  object_name text not null,                     -- Opportunity, Contact, Account / deals, contacts, companies
  field text not null,
  min_level smallint not null default 3 check (min_level between 2 and 4),
  primary key (source_system, object_name, field)
);
insert into public.external_field_allowlist values
  ('salesforce', 'Opportunity', 'StageName', 3),
  ('salesforce', 'Opportunity', 'CloseDate', 3),
  ('salesforce', 'Opportunity', 'Description', 3),
  ('salesforce', 'Contact', 'Title', 3),
  ('hubspot', 'deals', 'dealstage', 3),
  ('hubspot', 'deals', 'closedate', 3),
  ('hubspot', 'deals', 'description', 3),
  ('hubspot', 'contacts', 'jobtitle', 3);

create table public.outbound_changes (
  id bigint generated always as identity primary key,
  decision_id bigint not null references public.decisions(id),
  source_system text not null,
  object_name text not null,
  record_id text not null,
  field text not null,
  value jsonb not null,
  status text not null check (status in ('pending_approval','approved','sent','failed','cancelled')),
  approved_by uuid,
  sent_at timestamptz,
  error text,
  created_at timestamptz not null default now()
);

alter table public.sidecar_user_map enable row level security;
alter table public.sidecar_territory_map enable row level security;
alter table public.external_field_allowlist enable row level security;
alter table public.outbound_changes enable row level security;
create policy ea_user_map_select on public.sidecar_user_map for select to authenticated using (ea_private.current_role_name() in ('owner','manager'));
create policy ea_territory_map_select on public.sidecar_territory_map for select to authenticated using (ea_private.current_role_name() <> 'none');
create policy ea_ext_allowlist_select on public.external_field_allowlist for select to authenticated using (true);
create policy ea_outbound_select on public.outbound_changes for select to authenticated
  using (exists (select 1 from public.decisions d where d.id = decision_id));
grant select on public.sidecar_user_map, public.sidecar_territory_map, public.external_field_allowlist, public.outbound_changes to authenticated;
grant all on public.sidecar_user_map, public.sidecar_territory_map, public.external_field_allowlist, public.outbound_changes to service_role;
grant usage, select on all sequences in schema public to authenticated, service_role;
do $$
declare t text;
begin
  foreach t in array array['outbound_changes','sidecar_user_map','sidecar_territory_map','external_field_allowlist']
  loop
    execute format('create trigger ea_audit after insert or update or delete on public.%I
                    for each row execute function ea_private.audit()', t);
  end loop;
end $$;

-- Map an external CRM object to the subject type used by the primitives.
create or replace function ea_private.external_subject_type(p_system text, p_object text) returns text
language sql immutable set search_path = '' as $$
  select case lower(p_object)
    when 'opportunity' then 'deal' when 'deals' then 'deal'
    when 'contact' then 'contact' when 'contacts' then 'contact'
    when 'account' then 'company' when 'companies' then 'company' end
$$;

-- The agent-side door: propose a change to a field in the external CRM.
create or replace function public.propose_external_update(p_run_id bigint, p_decision_id bigint, p_system text,
  p_object text, p_record_id text, p_field text, p_value jsonb)
returns text language plpgsql security definer set search_path = '' as $$
declare a record; v_run public.runs; d public.decisions; v_min smallint; v_type text; v_status text;
begin
  select * into a from ea_private.agent_or_human(p_run_id, 'propose_external_update', 2::smallint, 'propose_external_update');
  v_run := a.run;
  if ea_private.current_kind() <> 'agent' then perform ea_private.raise_denied('humans edit the CRM directly'); end if;
  v_type := ea_private.external_subject_type(p_system, p_object);
  if v_type is null then perform ea_private.raise_denied('object not supported'); end if;
  d := ea_private.require_decision(v_run, p_decision_id, 'update_external_field', v_type, p_record_id);
  if d.payload->>'system' is distinct from p_system or d.payload->>'object' is distinct from p_object
     or d.payload->>'field' is distinct from p_field or (d.payload->'value') is distinct from p_value then
    perform ea_private.raise_denied('decision payload does not match this update');
  end if;
  select w.min_level into v_min from public.external_field_allowlist w
  where w.source_system = p_system and w.object_name = p_object and w.field = p_field;
  if v_min is null then perform ea_private.raise_denied(format('%s %s.%s is not on the external allowlist', p_system, p_object, p_field)); end if;
  if not ea_private.can_see_subject(v_type, p_record_id) then perform ea_private.raise_denied('record outside agent scope'); end if;
  if not exists (select 1 from public.decision_evidence de join public.evidence e on e.id = de.evidence_id
                 where de.decision_id = d.id and e.strength = 'strong' and e.superseded_by is null
                   and e.subject_type = v_type and e.subject_id = p_record_id) then
    perform ea_private.raise_denied('CRM changes need a decision that cites strong evidence about this record');
  end if;
  v_status := case when a.level >= v_min then 'approved' else 'pending_approval' end;
  insert into public.outbound_changes (decision_id, source_system, object_name, record_id, field, value, status)
  values (d.id, p_system, p_object, p_record_id, p_field, p_value, v_status);
  update public.decisions set status = case v_status when 'approved' then 'approved' else 'queued' end where id = d.id;
  return v_status;
end $$;

-- The worker-side door: the writeback worker (service role) claims approved changes and
-- reports what happened. Nothing else sends changes to the external CRM.
create or replace function public.claim_outbound_changes(p_system text, p_limit int default 50)
returns setof public.outbound_changes language plpgsql security definer set search_path = '' as $$
begin
  if auth.role() <> 'service_role' and current_user <> 'service_role' then
    perform ea_private.raise_denied('only the writeback worker claims outbound changes');
  end if;
  return query select * from public.outbound_changes
    where status = 'approved' and source_system = p_system order by id limit p_limit for update skip locked;
end $$;

create or replace function public.report_outbound_change(p_id bigint, p_ok boolean, p_error text default null)
returns void language plpgsql security definer set search_path = '' as $$
declare v_decision bigint;
begin
  if auth.role() <> 'service_role' and current_user <> 'service_role' then
    perform ea_private.raise_denied('only the writeback worker reports outbound changes');
  end if;
  update public.outbound_changes set status = case when p_ok then 'sent' else 'failed' end,
    sent_at = case when p_ok then now() end, error = p_error
  where id = p_id and status = 'approved'
  returning decision_id into v_decision;
  if v_decision is null then perform ea_private.raise_denied('change is not approved or does not exist'); end if;
  update public.decisions set status = case when p_ok then 'applied' else 'failed' end where id = v_decision;
end $$;

do $$
declare f record;
begin
  for f in select p.oid::regprocedure as sig from pg_proc p join pg_namespace n on n.oid = p.pronamespace
           where n.nspname = 'public' and p.proname in ('propose_external_update','claim_outbound_changes','report_outbound_change')
  loop
    execute format('revoke all on function %s from public, anon', f.sig);
    execute format('grant execute on function %s to authenticated, service_role', f.sig);
  end loop;
end $$;
