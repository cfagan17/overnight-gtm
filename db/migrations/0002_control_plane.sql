-- 0002 Control plane (Layer 2)
--
-- Replaces Atomic CRM's "any signed-in user can read, edit and delete everything"
-- policies (every policy was `using (true)`) with five mechanisms, all enforced in
-- Postgres so the UI, the REST API, MCP and agents get the same rules:
--
--   1. principals and roles     (humans and agents, each with their own identity)
--   2. record visibility        (ownership, management chain, territory, agent scope)
--   3. field-level security     (discount and partner margin columns are not selectable)
--   4. audit trail              (every ledger change, by whom, human or agent, and why)
--   5. agent grants             (named tools and scope per agent; agents cannot write tables directly)

-- 1. Principals ------------------------------------------------------------------

create table public.agent_definitions (
  id bigint generated always as identity primary key,
  name text unique not null,
  loop text not null,
  description text not null,
  autonomy_level smallint not null default 0 check (autonomy_level between 0 and 4),
  max_autonomy smallint not null default 4 check (max_autonomy between 0 and 4),
  model text,
  prompt_version text,
  active boolean not null default true,
  check (autonomy_level <= max_autonomy)
);

create table public.principals (
  user_id uuid primary key references auth.users(id),
  kind text not null check (kind in ('human','agent')),
  role text not null check (role in ('owner','manager','rep','readonly','agent')),
  manager_user_id uuid references public.principals(user_id),
  agent_definition_id bigint references public.agent_definitions(id),
  active boolean not null default true,
  check ((kind = 'agent') = (role = 'agent')),
  check ((kind = 'agent') = (agent_definition_id is not null))
);

-- Role of the caller. Falls back to Atomic's own model (administrator -> owner) so an
-- existing Atomic install keeps working before principals are filled in.
create or replace function ea_private.current_role_name() returns text
language sql stable security definer set search_path = '' as $$
  -- A principal row, active or not, always wins: deactivating someone revokes access.
  select case
    when exists (select 1 from public.principals p where p.user_id = auth.uid())
      then coalesce((select p.role from public.principals p where p.user_id = auth.uid() and p.active), 'none')
    else coalesce((select case when s.administrator then 'owner' else 'rep' end
                   from public.sales s where s.user_id = auth.uid() and not s.disabled), 'none')
  end
$$;

create or replace function ea_private.current_kind() returns text
language sql stable security definer set search_path = '' as $$
  select case
    when exists (select 1 from public.principals p where p.user_id = auth.uid())
      then coalesce((select p.kind from public.principals p where p.user_id = auth.uid() and p.active), 'none')
    else coalesce((select 'human' from public.sales s where s.user_id = auth.uid() and not s.disabled), 'none')
  end
$$;

create or replace function ea_private.current_sales_id() returns bigint
language sql stable security definer set search_path = '' as $$
  select s.id from public.sales s where s.user_id = auth.uid() and not s.disabled
$$;

create or replace function ea_private.current_agent_definition_id() returns bigint
language sql stable security definer set search_path = '' as $$
  select p.agent_definition_id from public.principals p
  where p.user_id = auth.uid() and p.active and p.kind = 'agent'
$$;

create or replace function ea_private.is_human() returns boolean
language sql stable set search_path = '' as $$ select ea_private.current_kind() = 'human' $$;

-- 2. Visibility -------------------------------------------------------------------

-- True when the record owner (a sales id) reports to the caller, at any depth.
create or replace function ea_private.manages(p_owner_sales_id bigint) returns boolean
language sql stable security definer set search_path = '' as $$
  with recursive chain(mgr, depth) as (
    select p.manager_user_id, 1
    from public.principals p join public.sales s on s.user_id = p.user_id
    where s.id = p_owner_sales_id
    union all
    select p.manager_user_id, c.depth + 1
    from public.principals p join chain c on p.user_id = c.mgr
    where c.mgr is not null and c.depth < 20
  )
  select p_owner_sales_id is not null and exists (select 1 from chain where mgr = auth.uid())
$$;

-- True when the caller is a member of the territory or of any ancestor territory.
create or replace function ea_private.in_my_territory(p_territory_id bigint) returns boolean
language sql stable security definer set search_path = '' as $$
  with recursive up(id, depth) as (
    select t.id, 1 from public.territories t where t.id = p_territory_id
    union all
    select t.parent_id, u.depth + 1 from public.territories t join up u on t.id = u.id
    where t.parent_id is not null and u.depth < 20
  )
  select p_territory_id is not null and exists (
    select 1 from public.territory_members tm
    join public.sales s on s.id = tm.sales_id
    where s.user_id = auth.uid() and tm.territory_id in (select id from up)
  )
$$;

-- 5. Agent grants (defined here because visibility for agents depends on them) -----

create table public.agent_grants (
  agent_definition_id bigint not null references public.agent_definitions(id) on delete cascade,
  tool text not null,
  scope jsonb not null default '{"all": false, "territory_ids": []}'::jsonb,
  approved_by uuid references auth.users(id),
  approved_at timestamptz,
  primary key (agent_definition_id, tool)
);

-- An agent sees a record when any of its approved grants covers the record's territory.
create or replace function ea_private.agent_scope_allows(p_territory_id bigint) returns boolean
language sql stable security definer set search_path = '' as $$
  select exists (
    select 1 from public.agent_grants g
    where g.agent_definition_id = ea_private.current_agent_definition_id()
      and g.approved_at is not null
      and (coalesce((g.scope->>'all')::boolean, false)
           or (p_territory_id is not null and g.scope->'territory_ids' @> to_jsonb(p_territory_id)))
  )
$$;

create or replace function ea_private.can_see(p_owner_sales_id bigint, p_territory_id bigint) returns boolean
language sql stable set search_path = '' as $$
  select case ea_private.current_role_name()
    when 'owner' then true
    when 'readonly' then true
    when 'manager' then p_owner_sales_id = ea_private.current_sales_id()
                        or ea_private.manages(p_owner_sales_id)
                        or ea_private.in_my_territory(p_territory_id)
    when 'rep' then p_owner_sales_id = ea_private.current_sales_id()
                    or ea_private.in_my_territory(p_territory_id)
    when 'agent' then ea_private.agent_scope_allows(p_territory_id)
    else false
  end
$$;

-- Direct edits are for humans only. Agents change the ledger through the agent
-- contract functions (0005), never through table writes.
create or replace function ea_private.can_edit(p_owner_sales_id bigint) returns boolean
language sql stable set search_path = '' as $$
  select ea_private.is_human() and case ea_private.current_role_name()
    when 'owner' then true
    when 'manager' then p_owner_sales_id = ea_private.current_sales_id() or ea_private.manages(p_owner_sales_id)
    when 'rep' then p_owner_sales_id = ea_private.current_sales_id()
    else false
  end
$$;

-- Deleting ledger records is reserved for owners and the record owner's managers.
-- Reps archive instead (deals.archived_at).
create or replace function ea_private.can_delete(p_owner_sales_id bigint) returns boolean
language sql stable set search_path = '' as $$
  select ea_private.is_human() and case ea_private.current_role_name()
    when 'owner' then true
    when 'manager' then ea_private.manages(p_owner_sales_id)
    else false
  end
$$;

-- Lookups used by child-table policies. Security definer so a policy can read the
-- parent's owner and territory without recursing through the parent's own policy.
create or replace function ea_private.company_owner_territory(p_company_id bigint, out owner bigint, out territory bigint)
language sql stable security definer set search_path = '' as $$
  select c.sales_id, c.territory_id from public.companies c where c.id = p_company_id
$$;
create or replace function ea_private.deal_owner_territory(p_deal_id bigint, out owner bigint, out territory bigint)
language sql stable security definer set search_path = '' as $$
  select d.sales_id, d.territory_id from public.deals d where d.id = p_deal_id
$$;
create or replace function ea_private.contact_owner_territory(p_contact_id bigint, out owner bigint, out territory bigint, out company_owner bigint)
language sql stable security definer set search_path = '' as $$
  select ct.sales_id, c.territory_id, c.sales_id
  from public.contacts ct left join public.companies c on c.id = ct.company_id
  where ct.id = p_contact_id
$$;

create or replace function ea_private.can_see_company(p_company_id bigint) returns boolean
language sql stable set search_path = '' as $$
  select coalesce((select ea_private.can_see(o.owner, o.territory) from ea_private.company_owner_territory(p_company_id) o), false)
$$;
create or replace function ea_private.can_see_deal(p_deal_id bigint) returns boolean
language sql stable set search_path = '' as $$
  select coalesce((select ea_private.can_see(o.owner, o.territory) from ea_private.deal_owner_territory(p_deal_id) o), false)
$$;
create or replace function ea_private.can_see_contact(p_contact_id bigint) returns boolean
language sql stable set search_path = '' as $$
  select coalesce((select ea_private.can_see(o.owner, o.territory) or ea_private.can_see(o.company_owner, o.territory)
                   from ea_private.contact_owner_territory(p_contact_id) o), false)
$$;
create or replace function ea_private.can_edit_deal(p_deal_id bigint) returns boolean
language sql stable set search_path = '' as $$
  select coalesce((select ea_private.can_edit(o.owner) from ea_private.deal_owner_territory(p_deal_id) o), false)
$$;
create or replace function ea_private.can_edit_contact(p_contact_id bigint) returns boolean
language sql stable set search_path = '' as $$
  select coalesce((select ea_private.can_edit(o.owner) or ea_private.can_edit(o.company_owner)
                   from ea_private.contact_owner_territory(p_contact_id) o), false)
$$;

grant execute on all functions in schema ea_private to authenticated, service_role;

-- Only owners move records between territories. For everyone else the territory comes from
-- the rules (companies) or the company (deals). Calls with no signed-in user (migrations,
-- the service role) are maintenance and pass through.
create or replace function ea_private.guard_territory() returns trigger
language plpgsql set search_path = '' as $$
begin
  if auth.uid() is null or ea_private.current_role_name() = 'owner' then
    return new;
  end if;
  if tg_op = 'INSERT' then
    new.territory_id := null;          -- the default triggers (named "20_...") fill it
  elsif new.territory_id is distinct from old.territory_id then
    raise exception 'ea: only owners change territory assignments' using errcode = '42501';
  end if;
  return new;
end $$;
create trigger "10_company_guard_territory" before insert or update on public.companies
  for each row execute function ea_private.guard_territory();
create trigger "10_deal_guard_territory" before insert or update on public.deals
  for each row execute function ea_private.guard_territory();

-- Replace every existing policy on the tables this migration governs ----------------

do $$
declare r record;
begin
  for r in
    select policyname, tablename from pg_policies
    where schemaname = 'public'
      and tablename in ('companies','contacts','contact_notes','deals','deal_notes','tasks','tags')
  loop
    execute format('drop policy %I on public.%I', r.policyname, r.tablename);
  end loop;
end $$;

-- companies
create policy ea_companies_select on public.companies for select to authenticated
  using (ea_private.can_see(sales_id, territory_id));
create policy ea_companies_insert on public.companies for insert to authenticated
  with check (ea_private.can_edit(sales_id));
create policy ea_companies_update on public.companies for update to authenticated
  using (ea_private.can_edit(sales_id)) with check (ea_private.can_edit(sales_id));
create policy ea_companies_delete on public.companies for delete to authenticated
  using (ea_private.can_delete(sales_id));

-- contacts: visible through their own owner or their company
create policy ea_contacts_select on public.contacts for select to authenticated
  using (ea_private.can_see(sales_id, (ea_private.company_owner_territory(company_id)).territory)
         or ea_private.can_see_company(company_id));
create policy ea_contacts_insert on public.contacts for insert to authenticated
  with check (ea_private.can_edit(sales_id)
              and (company_id is null or ea_private.can_edit((ea_private.company_owner_territory(company_id)).owner)));
create policy ea_contacts_update on public.contacts for update to authenticated
  using (ea_private.can_edit(sales_id) or ea_private.can_edit((ea_private.company_owner_territory(company_id)).owner))
  with check ((ea_private.can_edit(sales_id) or ea_private.can_edit((ea_private.company_owner_territory(company_id)).owner))
              and (company_id is null or ea_private.can_edit((ea_private.company_owner_territory(company_id)).owner)));
create policy ea_contacts_delete on public.contacts for delete to authenticated
  using (ea_private.can_delete(sales_id));

-- deals
create policy ea_deals_select on public.deals for select to authenticated
  using (ea_private.can_see(sales_id, territory_id));
create policy ea_deals_insert on public.deals for insert to authenticated
  with check (ea_private.can_edit(sales_id)
              and (company_id is null or ea_private.can_edit((ea_private.company_owner_territory(company_id)).owner)));
create policy ea_deals_update on public.deals for update to authenticated
  using (ea_private.can_edit(sales_id))
  with check (ea_private.can_edit(sales_id)
              and (company_id is null or ea_private.can_edit((ea_private.company_owner_territory(company_id)).owner)));
create policy ea_deals_delete on public.deals for delete to authenticated
  using (ea_private.can_delete(sales_id));

-- notes and tasks follow their parent; authors manage their own notes
create policy ea_contact_notes_select on public.contact_notes for select to authenticated
  using (ea_private.can_see_contact(contact_id));
create policy ea_contact_notes_insert on public.contact_notes for insert to authenticated
  with check (ea_private.is_human() and ea_private.can_see_contact(contact_id)
              and sales_id = ea_private.current_sales_id());
create policy ea_contact_notes_update on public.contact_notes for update to authenticated
  using (ea_private.is_human() and (sales_id = ea_private.current_sales_id() or ea_private.can_edit_contact(contact_id)))
  with check (ea_private.is_human() and ea_private.can_see_contact(contact_id));
create policy ea_contact_notes_delete on public.contact_notes for delete to authenticated
  using (ea_private.is_human() and (sales_id = ea_private.current_sales_id() or ea_private.can_delete((ea_private.contact_owner_territory(contact_id)).owner)));

create policy ea_deal_notes_select on public.deal_notes for select to authenticated
  using (ea_private.can_see_deal(deal_id));
create policy ea_deal_notes_insert on public.deal_notes for insert to authenticated
  with check (ea_private.is_human() and ea_private.can_see_deal(deal_id)
              and sales_id = ea_private.current_sales_id());
create policy ea_deal_notes_update on public.deal_notes for update to authenticated
  using (ea_private.is_human() and (sales_id = ea_private.current_sales_id() or ea_private.can_edit_deal(deal_id)))
  with check (ea_private.is_human() and ea_private.can_see_deal(deal_id));
create policy ea_deal_notes_delete on public.deal_notes for delete to authenticated
  using (ea_private.is_human() and (sales_id = ea_private.current_sales_id() or ea_private.can_delete((ea_private.deal_owner_territory(deal_id)).owner)));

create policy ea_tasks_select on public.tasks for select to authenticated
  using (ea_private.can_see_contact(contact_id));
create policy ea_tasks_insert on public.tasks for insert to authenticated
  with check (ea_private.is_human() and ea_private.can_see_contact(contact_id));
create policy ea_tasks_update on public.tasks for update to authenticated
  using (ea_private.is_human() and (sales_id = ea_private.current_sales_id() or ea_private.can_edit_contact(contact_id)))
  with check (ea_private.is_human() and ea_private.can_see_contact(contact_id));
create policy ea_tasks_delete on public.tasks for delete to authenticated
  using (ea_private.is_human() and (sales_id = ea_private.current_sales_id() or ea_private.can_edit_contact(contact_id)));

-- tags are a shared taxonomy: everyone reads, only owners and managers change them
create policy ea_tags_select on public.tags for select to authenticated using (true);
create policy ea_tags_write on public.tags for all to authenticated
  using (ea_private.is_human() and ea_private.current_role_name() in ('owner','manager'))
  with check (ea_private.is_human() and ea_private.current_role_name() in ('owner','manager'));

-- New ledger tables from 0001 --------------------------------------------------------

alter table public.territories enable row level security;
alter table public.territory_rules enable row level security;
alter table public.territory_members enable row level security;
alter table public.deal_contacts enable row level security;
alter table public.products enable row level security;
alter table public.deal_lines enable row level security;
alter table public.contracts enable row level security;
alter table public.partners enable row level security;
alter table public.deal_partners enable row level security;
alter table public.forecast_snapshots enable row level security;
alter table public.principals enable row level security;
alter table public.agent_definitions enable row level security;
alter table public.agent_grants enable row level security;

-- The territory carve is visible to everyone and changed only by owners (RevOps).
create policy ea_territories_select on public.territories for select to authenticated using (true);
create policy ea_territories_write on public.territories for all to authenticated
  using (ea_private.is_human() and ea_private.current_role_name() = 'owner')
  with check (ea_private.is_human() and ea_private.current_role_name() = 'owner');
create policy ea_territory_rules_select on public.territory_rules for select to authenticated using (true);
create policy ea_territory_rules_write on public.territory_rules for all to authenticated
  using (ea_private.is_human() and ea_private.current_role_name() = 'owner')
  with check (ea_private.is_human() and ea_private.current_role_name() = 'owner');
create policy ea_territory_members_select on public.territory_members for select to authenticated using (true);
create policy ea_territory_members_write on public.territory_members for all to authenticated
  using (ea_private.is_human() and ea_private.current_role_name() = 'owner')
  with check (ea_private.is_human() and ea_private.current_role_name() = 'owner');

create policy ea_products_select on public.products for select to authenticated using (true);
create policy ea_products_write on public.products for all to authenticated
  using (ea_private.is_human() and ea_private.current_role_name() = 'owner')
  with check (ea_private.is_human() and ea_private.current_role_name() = 'owner');

create policy ea_deal_contacts_select on public.deal_contacts for select to authenticated
  using (ea_private.can_see_deal(deal_id));
create policy ea_deal_contacts_write on public.deal_contacts for all to authenticated
  using (ea_private.can_edit_deal(deal_id)) with check (ea_private.can_edit_deal(deal_id));

create policy ea_deal_lines_select on public.deal_lines for select to authenticated
  using (ea_private.can_see_deal(deal_id));
create policy ea_deal_lines_write on public.deal_lines for all to authenticated
  using (ea_private.can_edit_deal(deal_id)) with check (ea_private.can_edit_deal(deal_id));

create policy ea_contracts_select on public.contracts for select to authenticated
  using (ea_private.can_see_company(company_id));
create policy ea_contracts_write on public.contracts for all to authenticated
  using (ea_private.is_human() and ea_private.current_role_name() in ('owner','manager') and ea_private.can_see_company(company_id))
  with check (ea_private.is_human() and ea_private.current_role_name() in ('owner','manager') and ea_private.can_see_company(company_id));

create policy ea_partners_select on public.partners for select to authenticated
  using (ea_private.current_role_name() <> 'none');
create policy ea_partners_write on public.partners for all to authenticated
  using (ea_private.is_human() and (ea_private.current_role_name() = 'owner'
         or partner_manager_sales_id = ea_private.current_sales_id()))
  with check (ea_private.is_human() and (ea_private.current_role_name() = 'owner'
         or partner_manager_sales_id = ea_private.current_sales_id()));

create policy ea_deal_partners_select on public.deal_partners for select to authenticated
  using (ea_private.can_see_deal(deal_id));
create policy ea_deal_partners_write on public.deal_partners for all to authenticated
  using (ea_private.can_edit_deal(deal_id)) with check (ea_private.can_edit_deal(deal_id));

create policy ea_forecast_snapshots_select on public.forecast_snapshots for select to authenticated
  using (ea_private.current_role_name() in ('owner','readonly')
         or ea_private.can_see(sales_id, territory_id));

create policy ea_principals_select on public.principals for select to authenticated
  using (user_id = auth.uid() or ea_private.current_role_name() in ('owner','manager'));
create policy ea_principals_write on public.principals for all to authenticated
  using (ea_private.is_human() and ea_private.current_role_name() = 'owner')
  with check (ea_private.is_human() and ea_private.current_role_name() = 'owner');

create policy ea_agent_definitions_select on public.agent_definitions for select to authenticated
  using (ea_private.current_role_name() <> 'none');
create policy ea_agent_definitions_write on public.agent_definitions for all to authenticated
  using (ea_private.is_human() and ea_private.current_role_name() = 'owner')
  with check (ea_private.is_human() and ea_private.current_role_name() = 'owner');

create policy ea_agent_grants_select on public.agent_grants for select to authenticated
  using (ea_private.current_role_name() = 'owner'
         or agent_definition_id = ea_private.current_agent_definition_id());
create policy ea_agent_grants_write on public.agent_grants for all to authenticated
  using (ea_private.is_human() and ea_private.current_role_name() = 'owner')
  with check (ea_private.is_human() and ea_private.current_role_name() = 'owner');

-- Autonomy changes only through the promotion review (0006), never by editing the row.
create or replace function ea_private.guard_autonomy() returns trigger
language plpgsql set search_path = '' as $$
begin
  -- The loop name ties an agent to its caps, holdouts and review history. It never changes.
  if new."loop" is distinct from old."loop" then
    raise exception 'ea: an agent definition''s loop cannot change; create a new agent instead' using errcode = '42501';
  end if;
  if new.autonomy_level is distinct from old.autonomy_level
     and coalesce(current_setting('ea.promotion_in_progress', true), '') <> 'on' then
    raise exception 'ea: autonomy_level changes only through public.decide_promotion()' using errcode = '42501';
  end if;
  return new;
end $$;
create trigger ea_guard_autonomy before update on public.agent_definitions
  for each row execute function ea_private.guard_autonomy();

-- 3. Field-level security -------------------------------------------------------------
-- discount_pct and margin_pct are not selectable by API roles. Owners and managers read
-- them through functions that check role and visibility.

revoke select on public.deal_lines from authenticated;
grant select (id, deal_id, product_id, quantity, arr_usd) on public.deal_lines to authenticated;
revoke select on public.partners from authenticated;
grant select (id, name, partner_type, tier, website, partner_manager_sales_id, status) on public.partners to authenticated;

create or replace function public.deal_line_discounts(p_deal_id bigint)
returns table (line_id bigint, discount_pct numeric)
language sql stable security definer set search_path = '' as $$
  select l.id, l.discount_pct from public.deal_lines l
  where l.deal_id = p_deal_id
    and ea_private.current_role_name() in ('owner','manager')
    and ea_private.can_see_deal(p_deal_id)
$$;

create or replace function public.partner_margin(p_partner_id bigint) returns numeric
language sql stable security definer set search_path = '' as $$
  select p.margin_pct from public.partners p
  where p.id = p_partner_id
    and ea_private.is_human()
    and (ea_private.current_role_name() = 'owner' or p.partner_manager_sales_id = ea_private.current_sales_id())
$$;

-- 4. Audit trail -----------------------------------------------------------------

create table public.audit_log (
  id bigint generated always as identity primary key,
  table_name text not null,
  row_id text,
  op text not null,
  before jsonb,
  after jsonb,
  principal_id uuid,
  principal_kind text,
  decision_id bigint,          -- set when an agent contract function made the change (0005)
  run_id bigint,
  at timestamptz not null default now()
);
alter table public.audit_log enable row level security;
create policy ea_audit_select on public.audit_log for select to authenticated
  using (ea_private.current_role_name() in ('owner','readonly'));
-- No insert, update or delete policy: only the trigger (security definer) writes it.

create or replace function ea_private.audit() returns trigger
language plpgsql security definer set search_path = '' as $$
declare
  v_decision bigint := nullif(current_setting('ea.decision_id', true), '')::bigint;
  v_run bigint := nullif(current_setting('ea.run_id', true), '')::bigint;
  v_row jsonb := case when tg_op = 'DELETE' then to_jsonb(old) else to_jsonb(new) end;
  -- Masked columns never enter the log, or the log would undo the field-level security.
  v_masked text[] := case tg_table_name when 'deal_lines' then array['discount_pct']
                                        when 'partners' then array['margin_pct'] else array[]::text[] end;
begin
  -- Anyone can set a session variable, so ea.decision_id is only recorded when it names
  -- a decision that is being applied right now (status 'applying', set by the contract
  -- function in the same transaction) and was made by the current principal.
  if v_decision is not null and not exists (
       select 1 from public.decisions d
       where d.id = v_decision and d.status = 'applying'
         and (d.made_by = auth.uid() or d.reviewed_by = auth.uid())) then
    v_decision := null;
    v_run := null;
  end if;
  insert into public.audit_log (table_name, row_id, op, before, after, principal_id, principal_kind, decision_id, run_id)
  values (tg_table_name, v_row->>'id', tg_op,
          case when tg_op in ('UPDATE','DELETE') then to_jsonb(old) - v_masked end,
          case when tg_op in ('INSERT','UPDATE') then to_jsonb(new) - v_masked end,
          auth.uid(), ea_private.current_kind(), v_decision, v_run);
  return null;
end $$;

do $$
declare t text;
begin
  foreach t in array array['companies','contacts','deals','deal_lines','deal_contacts','contracts',
                           'partners','deal_partners','territories','territory_rules','territory_members',
                           'principals','agent_definitions','agent_grants']
  loop
    execute format('create trigger ea_audit after insert or update or delete on public.%I
                    for each row execute function ea_private.audit()', t);
  end loop;
end $$;

-- Grants ------------------------------------------------------------------------
-- Atomic grants every table to anon. RLS already blocks anon (policies are "to
-- authenticated"), but grants are removed too so a future permissive policy cannot
-- expose data to signed-out callers. The login page's init_state view stays readable.

revoke all on all tables in schema public from anon;
grant select on public.init_state to anon;

grant select, insert, update, delete on public.territories, public.territory_rules, public.territory_members,
  public.deal_contacts, public.products, public.contracts, public.deal_partners,
  public.principals, public.agent_definitions, public.agent_grants to authenticated;
grant insert, update, delete on public.deal_lines, public.partners to authenticated;
grant select on public.forecast_snapshots, public.audit_log to authenticated;
grant all on all tables in schema public to service_role;
grant usage, select on all sequences in schema public to authenticated, service_role;
grant execute on function public.take_forecast_snapshot(date), public.deal_line_discounts(bigint),
  public.partner_margin(bigint) to authenticated, service_role;
revoke execute on function public.take_forecast_snapshot(date), public.deal_line_discounts(bigint),
  public.partner_margin(bigint) from anon, public;

-- Hygiene found by tools/rls-audit ------------------------------------------------------
-- favicons_excluded_domains had an unconditional ALL policy. Everyone reads it, owners change it.
do $$
declare r record;
begin
  for r in select policyname from pg_policies where schemaname = 'public' and tablename = 'favicons_excluded_domains' loop
    execute format('drop policy %I on public.favicons_excluded_domains', r.policyname);
  end loop;
end $$;
create policy ea_favicons_select on public.favicons_excluded_domains for select to authenticated using (true);
create policy ea_favicons_write on public.favicons_excluded_domains for all to authenticated
  using (ea_private.is_human() and ea_private.current_role_name() = 'owner')
  with check (ea_private.is_human() and ea_private.current_role_name() = 'owner');

-- Signed-out callers need no functions in the public schema. Functions signed-in users can
-- run today get an explicit grant first, so removing the PUBLIC default changes nothing for them.
do $$
declare f record;
begin
  for f in select p.oid::regprocedure as sig, has_function_privilege('authenticated', p.oid, 'execute') as auth_ok
           from pg_proc p join pg_namespace n on n.oid = p.pronamespace where n.nspname = 'public'
  loop
    if f.auth_ok then execute format('grant execute on function %s to authenticated', f.sig); end if;
    execute format('revoke execute on function %s from public, anon', f.sig);
  end loop;
end $$;
grant execute on all functions in schema public to service_role;
