-- 0001 Ledger (Layer 1)
--
-- Extends Atomic CRM's tables (companies, contacts, deals, sales) with what a company
-- past founder-led sales needs: territories, buying-group roles, products and lines,
-- contracts, partners and weekly forecast snapshots.
--
-- Requires: Atomic CRM schema (vendor/atomic-crm/schemas) already applied.

-- Supabase grants every new table in public to anon and authenticated by default. Tables
-- created by these migrations get only the grants they state explicitly, so switch that
-- default off while they run. 0008_final_grants.sql switches it back on.
alter default privileges in schema public revoke all on tables from anon, authenticated;
alter default privileges in schema public revoke all on sequences from anon, authenticated;

create schema if not exists ea_private;
revoke all on schema ea_private from public;
grant usage on schema ea_private to authenticated, service_role;

-- Territories -------------------------------------------------------------------

create table public.territories (
  id bigint generated always as identity primary key,
  name text not null,
  segment text not null check (segment in ('enterprise','mid_market','commercial','smb','strategic')),
  region text,
  parent_id bigint references public.territories(id),
  owner_sales_id bigint references public.sales(id),
  effective_from date not null default current_date,
  effective_to date,                          -- null = part of the current carve
  check (effective_to is null or effective_to > effective_from)
);

-- Rules assign accounts to territories. Lowest priority number wins.
-- match example: {"state_abbr": ["CA","OR","WA"], "segment": "enterprise"}
create table public.territory_rules (
  id bigint generated always as identity primary key,
  territory_id bigint not null references public.territories(id) on delete cascade,
  priority int not null,
  match jsonb not null,
  unique (territory_id, priority)
);

-- Who works a territory. 'owner' carries quota, 'member' and 'overlay' can read it.
create table public.territory_members (
  territory_id bigint not null references public.territories(id) on delete cascade,
  sales_id bigint not null references public.sales(id),
  member_role text not null default 'member' check (member_role in ('owner','member','overlay')),
  primary key (territory_id, sales_id)
);

alter table public.companies
  add column territory_id bigint references public.territories(id),
  add column segment text check (segment in ('enterprise','mid_market','commercial','smb','strategic')),
  add column parent_company_id bigint references public.companies(id);

alter table public.deals
  add column territory_id bigint references public.territories(id),
  add column forecast_category text not null default 'pipeline'
    check (forecast_category in ('pipeline','best_case','commit','closed','omitted')),
  add column source text check (source in ('inbound','outbound','partner','expansion','renewal','self_serve','event','other'));

create index companies_territory_idx on public.companies (territory_id);
create index deals_territory_idx on public.deals (territory_id);
create index deals_sales_idx on public.deals (sales_id);
create index companies_sales_idx on public.companies (sales_id);
create index contacts_sales_idx on public.contacts (sales_id);

-- Assign a company to the first matching current territory.
create or replace function ea_private.match_territory(p_company public.companies)
returns bigint language sql stable set search_path = '' as $$
  select r.territory_id
  from public.territory_rules r
  join public.territories t on t.id = r.territory_id
  where (t.effective_to is null or t.effective_to > current_date)
    and t.effective_from <= current_date
    and (not (r.match ? 'state_abbr') or p_company.state_abbr = any (array(select jsonb_array_elements_text(r.match->'state_abbr'))))
    and (not (r.match ? 'country')    or p_company.country    = any (array(select jsonb_array_elements_text(r.match->'country'))))
    and (not (r.match ? 'segment')    or p_company.segment    = r.match->>'segment')
  order by r.priority
  limit 1
$$;

create or replace function ea_private.company_territory_default() returns trigger
language plpgsql set search_path = '' as $$
begin
  if new.territory_id is null then
    new.territory_id := ea_private.match_territory(new);
  end if;
  return new;
end $$;

create trigger "20_company_territory_default"
  before insert or update of state_abbr, country, segment on public.companies
  for each row execute function ea_private.company_territory_default();

-- Deals inherit their company's territory unless set explicitly.
create or replace function ea_private.deal_territory_default() returns trigger
language plpgsql security definer set search_path = '' as $$
begin
  if new.territory_id is null and new.company_id is not null then
    select c.territory_id into new.territory_id from public.companies c where c.id = new.company_id;
  end if;
  return new;
end $$;

create trigger "20_deal_territory_default"
  before insert or update of company_id on public.deals
  for each row execute function ea_private.deal_territory_default();

-- Buying group ------------------------------------------------------------------

create table public.deal_contacts (
  deal_id bigint not null references public.deals(id) on delete cascade,
  contact_id bigint not null references public.contacts(id) on delete cascade,
  buying_role text not null check (buying_role in
    ('champion','economic_buyer','decision_maker','technical_buyer','influencer','blocker','user','procurement','legal')),
  primary key (deal_id, contact_id, buying_role)
);

-- Products, lines, contracts ------------------------------------------------------

create table public.products (
  id bigint generated always as identity primary key,
  sku text unique not null,
  name text not null,
  pricing_model text not null check (pricing_model in ('subscription','usage','one_time','services')),
  list_price_usd numeric,
  active boolean not null default true
);

create table public.deal_lines (
  id bigint generated always as identity primary key,
  deal_id bigint not null references public.deals(id) on delete cascade,
  product_id bigint not null references public.products(id),
  quantity numeric not null check (quantity > 0),
  arr_usd numeric not null check (arr_usd >= 0),
  discount_pct numeric not null default 0 check (discount_pct between 0 and 100)  -- masked, see 0002
);
create index deal_lines_deal_idx on public.deal_lines (deal_id);

create table public.contracts (
  id bigint generated always as identity primary key,
  company_id bigint not null references public.companies(id) on delete cascade,
  deal_id bigint references public.deals(id),
  starts_on date not null,
  ends_on date not null,
  arr_usd numeric not null,
  auto_renew boolean not null default false,
  status text not null default 'active' check (status in ('draft','active','expired','terminated')),
  check (ends_on > starts_on)
);
create index contracts_company_idx on public.contracts (company_id);

-- Partners ----------------------------------------------------------------------

create table public.partners (
  id bigint generated always as identity primary key,
  name text not null,
  partner_type text not null check (partner_type in ('reseller','referral','technology','cloud_marketplace','si','agency')),
  tier text,
  website text,
  margin_pct numeric check (margin_pct between 0 and 100),   -- masked, see 0002
  partner_manager_sales_id bigint references public.sales(id),
  status text not null default 'active' check (status in ('prospect','active','inactive'))
);

create table public.deal_partners (
  deal_id bigint not null references public.deals(id) on delete cascade,
  partner_id bigint not null references public.partners(id),
  credit text not null check (credit in ('sourced','influenced','resold','fulfilled')),
  primary key (deal_id, partner_id, credit)
);

-- Forecast snapshots (append-only) -------------------------------------------------

create table public.forecast_snapshots (
  snapshot_week date not null,
  deal_id bigint not null,
  stage text,
  forecast_category text,
  amount_usd numeric,
  expected_closing_date date,
  sales_id bigint,
  territory_id bigint,
  taken_at timestamptz not null default now(),
  primary key (snapshot_week, deal_id)
);

-- Freeze the open pipeline for a week. Idempotent per week. Run weekly (pg_cron or a loop).
create or replace function public.take_forecast_snapshot(p_week date default date_trunc('week', current_date)::date)
returns int language plpgsql security definer set search_path = '' as $$
declare n int;
begin
  if not (ea_private.current_role_name() in ('owner','manager') or auth.role() = 'service_role') then
    raise exception 'ea: only owners, managers or the service role take snapshots' using errcode = '42501';
  end if;
  insert into public.forecast_snapshots (snapshot_week, deal_id, stage, forecast_category, amount_usd,
                                         expected_closing_date, sales_id, territory_id)
  select p_week, d.id, d.stage, d.forecast_category, d.amount, d.expected_closing_date, d.sales_id, d.territory_id
  from public.deals d
  where d.archived_at is null
  on conflict (snapshot_week, deal_id) do nothing;
  get diagnostics n = row_count;
  return n;
end $$;
