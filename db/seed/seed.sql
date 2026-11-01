-- Demo seed: a fictional company, "Northwind Data", selling a data platform.
-- Every company, person and partner here is invented. Run as a superuser or the
-- service role on a fresh database after the migrations. Fixed UUIDs keep tests stable.

begin;

-- Humans ------------------------------------------------------------------------
-- The first auth user becomes Atomic's administrator. Later users need an invitation.
insert into auth.users (id, email, raw_user_meta_data) values
  ('00000000-0000-0000-0000-000000000001', 'riley.ops@northwind.example', '{"first_name":"Riley","last_name":"Ops"}');

insert into public.user_invitations (user_id) values
  ('00000000-0000-0000-0000-000000000002'), ('00000000-0000-0000-0000-000000000003'),
  ('00000000-0000-0000-0000-000000000004'), ('00000000-0000-0000-0000-000000000005'),
  ('00000000-0000-0000-0000-000000000006'), ('00000000-0000-0000-0000-000000000007'),
  ('00000000-0000-0000-0000-000000000008'), ('00000000-0000-0000-0000-000000000009');

insert into auth.users (id, email, raw_user_meta_data) values
  ('00000000-0000-0000-0000-000000000002', 'vic.vp@northwind.example',      '{"first_name":"Vic","last_name":"VP Sales"}'),
  ('00000000-0000-0000-0000-000000000003', 'wen.west@northwind.example',    '{"first_name":"Wen","last_name":"West Manager"}'),
  ('00000000-0000-0000-0000-000000000004', 'ezra.east@northwind.example',   '{"first_name":"Ezra","last_name":"East Manager"}'),
  ('00000000-0000-0000-0000-000000000005', 'ana.rep@northwind.example',     '{"first_name":"Ana","last_name":"West Enterprise AE"}'),
  ('00000000-0000-0000-0000-000000000006', 'ben.rep@northwind.example',     '{"first_name":"Ben","last_name":"West Commercial AE"}'),
  ('00000000-0000-0000-0000-000000000007', 'cy.rep@northwind.example',      '{"first_name":"Cy","last_name":"East AE"}'),
  ('00000000-0000-0000-0000-000000000008', 'pat.partners@northwind.example','{"first_name":"Pat","last_name":"Partner Manager"}'),
  ('00000000-0000-0000-0000-000000000009', 'fin.readonly@northwind.example','{"first_name":"Fin","last_name":"Finance"}');

insert into public.principals (user_id, kind, role, manager_user_id) values
  ('00000000-0000-0000-0000-000000000001', 'human', 'owner',    null),
  ('00000000-0000-0000-0000-000000000002', 'human', 'manager',  null),
  ('00000000-0000-0000-0000-000000000003', 'human', 'manager',  '00000000-0000-0000-0000-000000000002'),
  ('00000000-0000-0000-0000-000000000004', 'human', 'manager',  '00000000-0000-0000-0000-000000000002'),
  ('00000000-0000-0000-0000-000000000005', 'human', 'rep',      '00000000-0000-0000-0000-000000000003'),
  ('00000000-0000-0000-0000-000000000006', 'human', 'rep',      '00000000-0000-0000-0000-000000000003'),
  ('00000000-0000-0000-0000-000000000007', 'human', 'rep',      '00000000-0000-0000-0000-000000000004'),
  ('00000000-0000-0000-0000-000000000008', 'human', 'rep',      '00000000-0000-0000-0000-000000000002'),
  ('00000000-0000-0000-0000-000000000009', 'human', 'readonly', null);

-- Territories ----------------------------------------------------------------------
insert into public.territories (name, segment, region, parent_id, owner_sales_id) values
  ('AMER',               'strategic',  'AMER', null, (select id from public.sales where email = 'vic.vp@northwind.example'));
insert into public.territories (name, segment, region, parent_id, owner_sales_id) values
  ('West Enterprise',    'enterprise', 'West', 1, (select id from public.sales where email = 'ana.rep@northwind.example')),
  ('West Commercial',    'commercial', 'West', 1, (select id from public.sales where email = 'ben.rep@northwind.example')),
  ('East Enterprise',    'enterprise', 'East', 1, (select id from public.sales where email = 'cy.rep@northwind.example')),
  ('East Commercial',    'commercial', 'East', 1, (select id from public.sales where email = 'cy.rep@northwind.example'));

insert into public.territory_rules (territory_id, priority, match) values
  (2, 10, '{"state_abbr": ["CA","OR","WA","NV","AZ","CO","UT"], "segment": "enterprise"}'),
  (3, 20, '{"state_abbr": ["CA","OR","WA","NV","AZ","CO","UT"]}'),
  (4, 30, '{"state_abbr": ["NY","MA","NJ","PA","IL","GA","TX"], "segment": "enterprise"}'),
  (5, 40, '{"state_abbr": ["NY","MA","NJ","PA","IL","GA","TX"]}');

insert into public.territory_members (territory_id, sales_id, member_role)
select 2, id, 'owner' from public.sales where email = 'ana.rep@northwind.example' union all
select 3, id, 'owner' from public.sales where email = 'ben.rep@northwind.example' union all
select 4, id, 'owner' from public.sales where email = 'cy.rep@northwind.example' union all
select 5, id, 'owner' from public.sales where email = 'cy.rep@northwind.example';

-- Products and partners --------------------------------------------------------------
insert into public.products (sku, name, pricing_model, list_price_usd) values
  ('NW-PLAT', 'Northwind Platform', 'subscription', 60000),
  ('NW-USAGE', 'Compute credits', 'usage', 1),
  ('NW-SSO', 'Enterprise security add-on', 'subscription', 15000),
  ('NW-PS', 'Onboarding services', 'services', 20000);

insert into public.partners (name, partner_type, tier, website, margin_pct, partner_manager_sales_id) values
  ('Harbor Systems Integrators', 'si', 'gold', 'https://harbor-si.example', 15, (select id from public.sales where email = 'pat.partners@northwind.example')),
  ('Cobalt Cloud Marketplace', 'cloud_marketplace', null, 'https://cobalt-cloud.example', 3, (select id from public.sales where email = 'pat.partners@northwind.example')),
  ('Juniper Resale', 'reseller', 'silver', 'https://juniper-resale.example', 20, (select id from public.sales where email = 'pat.partners@northwind.example')),
  ('Fernway Analytics', 'technology', null, 'https://fernway.example', null, (select id from public.sales where email = 'pat.partners@northwind.example'));

-- Companies, contacts, deals ------------------------------------------------------------
-- 24 fictional accounts across the four territories, owned by the territory's AE.
with names(n, name, state, seg) as (values
  (1,'Acme Orchards','CA','enterprise'),(2,'Bluebird Freight','WA','enterprise'),(3,'Cedar Health','OR','enterprise'),
  (4,'Dune Robotics','AZ','enterprise'),(5,'Ember Media','CA','enterprise'),(6,'Fjord Logistics','CO','enterprise'),
  (7,'Granite Labs','CA','commercial'),(8,'Hollow Pine Studio','OR','commercial'),(9,'Iris Payments','WA','commercial'),
  (10,'Jetty Foods','NV','commercial'),(11,'Kestrel Bikes','UT','commercial'),(12,'Lumen Clinics','CA','commercial'),
  (13,'Maple Ledger','NY','enterprise'),(14,'Northgate Insurance','MA','enterprise'),(15,'Orchid Pharma','NJ','enterprise'),
  (16,'Pioneer Grid','TX','enterprise'),(17,'Quarry Capital','IL','enterprise'),(18,'Riverbend Retail','GA','enterprise'),
  (19,'Sable Coffee','NY','commercial'),(20,'Tidewater Tours','MA','commercial'),(21,'Umber Print','PA','commercial'),
  (22,'Vale Fitness','TX','commercial'),(23,'Willow Legal','IL','commercial'),(24,'Yarrow Farms','GA','commercial'))
insert into public.companies (name, state_abbr, country, segment, sector, sales_id, website)
select name, state, 'US', seg, 'Technology',
  (select s.id from public.sales s where s.email = case
     when state in ('CA','OR','WA','NV','AZ','CO','UT') and seg = 'enterprise' then 'ana.rep@northwind.example'
     when state in ('CA','OR','WA','NV','AZ','CO','UT') then 'ben.rep@northwind.example'
     else 'cy.rep@northwind.example' end),
  'https://' || lower(replace(name, ' ', '')) || '.example'
from names order by n;

insert into public.contacts (first_name, last_name, title, company_id, sales_id, email_jsonb, status)
select fn, 'Contact ' || c.id, t, c.id, c.sales_id,
  jsonb_build_array(jsonb_build_object('email', lower(fn) || '.' || c.id || '@' || replace(substr(c.website, 9), '/', ''), 'type', 'Work')),
  'warm'
from public.companies c
cross join (values ('Jordan','VP Engineering'), ('Sam','Head of Data'), ('Casey','Director of Procurement')) v(fn, t);

insert into public.deals (name, company_id, stage, amount, sales_id, expected_closing_date, forecast_category, source)
select c.name || ' - Platform', c.id,
  (array['opportunity','proposal-sent','in-negociation','won','lost'])[1 + (c.id % 5)],
  case when c.segment = 'enterprise' then 120000 + c.id * 5000 else 30000 + c.id * 1000 end,
  c.sales_id, current_date + (c.id * 7)::int,
  (array['pipeline','best_case','commit','closed','omitted'])[1 + (c.id % 5)],
  (array['outbound','inbound','partner','expansion'])[1 + (c.id % 4)]
from public.companies c;

insert into public.deal_lines (deal_id, product_id, quantity, arr_usd, discount_pct)
select d.id, 1, 1, d.amount * 0.8, (d.id % 4) * 5 from public.deals d;
insert into public.deal_lines (deal_id, product_id, quantity, arr_usd, discount_pct)
select d.id, 3, 1, d.amount * 0.2, 0 from public.deals d join public.companies c on c.id = d.company_id where c.segment = 'enterprise';

insert into public.deal_contacts (deal_id, contact_id, buying_role)
select d.id, ct.id, case ct.title when 'VP Engineering' then 'economic_buyer' when 'Head of Data' then 'champion' else 'procurement' end
from public.deals d join public.contacts ct on ct.company_id = d.company_id;

insert into public.deal_partners (deal_id, partner_id, credit)
select d.id, 1 + (d.id % 3), case when d.id % 2 = 0 then 'sourced' else 'influenced' end
from public.deals d where d.source = 'partner';

insert into public.contracts (company_id, deal_id, starts_on, ends_on, arr_usd, auto_renew)
select d.company_id, d.id, current_date - 200, current_date + 165, d.amount, d.id % 2 = 0
from public.deals d where d.stage = 'won';

-- Agents: one auth user and principal per loop -------------------------------------------
-- max_autonomy: comp ops and territory design never pass level 2 (pay needs a human signature).
insert into public.agent_definitions (name, loop, description, autonomy_level, max_autonomy, model, prompt_version) values
  ('market-model',          'market_model',          'Scores every account against the ICP weekly',                       1, 4, 'claude-model', 'v1'),
  ('account-program',       'account_program',       'Writes the approach plan for one account',                          1, 4, 'claude-model', 'v1'),
  ('outreach',              'outreach',              'Runs approved strategy steps as touches',                            2, 4, 'claude-model', 'v1'),
  ('conversation-capture',  'conversation_capture',  'Turns calls and emails into evidence, commitments, field updates',    1, 4, 'claude-model', 'v1'),
  ('deal-inspection',       'deal_inspection',       'Flags slipping deals and proposes next steps',                       1, 4, 'claude-model', 'v1'),
  ('forecast',              'forecast',              'Makes a forecast call by segment with rationale',                    0, 3, 'claude-model', 'v1'),
  ('post-sale-health',      'post_sale_health',      'Scores account health and flags expansion and churn',                1, 4, 'claude-model', 'v1'),
  ('partner-intelligence',  'partner_intelligence',  'Reviews partner activity and the ecosystem, proposes partner plays',  1, 4, 'claude-model', 'v1'),
  ('product-feedback',      'product_feedback',      'Themes product feedback from conversations for the product team',    2, 4, 'claude-model', 'v1'),
  ('territory-capacity',    'territory_capacity',    'Proposes the territory carve and capacity model',                    1, 2, 'claude-model', 'v1'),
  ('comp-ops',              'comp_ops',              'Proposes credit splits and payout calculations',                     1, 2, 'claude-model', 'v1'),
  ('operating-design',      'operating_design',      'Proposes changes to stages, methodology skills and the human-agent split', 1, 2, 'claude-model', 'v1');

insert into public.user_invitations (user_id)
select ('00000000-0000-0000-0000-0000000001' || lpad(id::text, 2, '0'))::uuid from public.agent_definitions;
insert into auth.users (id, email, raw_app_meta_data)
select ('00000000-0000-0000-0000-0000000001' || lpad(id::text, 2, '0'))::uuid, name || '@agents.northwind.example', '{"ea_kind":"agent"}'
from public.agent_definitions;
insert into public.principals (user_id, kind, role, agent_definition_id)
select ('00000000-0000-0000-0000-0000000001' || lpad(id::text, 2, '0'))::uuid, 'agent', 'agent', id from public.agent_definitions;

-- Grants. The account-program agent only covers West Enterprise (territory 2); the others are org-wide.
insert into public.agent_grants (agent_definition_id, tool, scope, approved_by, approved_at)
select d.id, t.tool,
  case when d.name = 'account-program' then '{"all": false, "territory_ids": [2]}'::jsonb else '{"all": true}'::jsonb end,
  '00000000-0000-0000-0000-000000000001', now()
from public.agent_definitions d
cross join (values ('get_account_context'), ('search_evidence'), ('get_policies'), ('record_evidence'),
                   ('propose_decision'), ('propose_strategy'), ('create_commitment'), ('escalate')) t(tool);

insert into public.agent_grants (agent_definition_id, tool, scope, approved_by, approved_at)
select id, 'apply_field_update', '{"all": true}', '00000000-0000-0000-0000-000000000001', now()
from public.agent_definitions where name in ('conversation-capture', 'deal-inspection');
insert into public.agent_grants (agent_definition_id, tool, scope, approved_by, approved_at)
select id, 'schedule_touch', '{"all": true}', '00000000-0000-0000-0000-000000000001', now()
from public.agent_definitions where name = 'outreach';
insert into public.agent_grants (agent_definition_id, tool, scope, approved_by, approved_at)
select id, 'propose_skill_version', '{"all": true}', '00000000-0000-0000-0000-000000000001', now()
from public.agent_definitions where name = 'operating-design';

-- A draft experiment: 20% of West Enterprise accounts held out from AI account programs.
insert into public.experiments (name, hypothesis, loop, metric, subject_type, holdout_pct, created_by) values
  ('AI account programs, West Enterprise', 'AI-written account programs book more first meetings within 60 days',
   'account_program', 'meeting_booked_within_60d', 'company', 20, '00000000-0000-0000-0000-000000000001');

commit;

-- Notes and tasks, so the attack suite has something to aim at.
insert into public.contact_notes (contact_id, text, sales_id)
select ct.id, 'Call notes: budget approved for Q1', ct.sales_id from public.contacts ct where ct.first_name = 'Jordan';
insert into public.tasks (contact_id, type, text, sales_id, due_date)
select ct.id, 'call', 'Follow up on pricing', ct.sales_id, now() + interval '3 days' from public.contacts ct where ct.first_name = 'Jordan';

-- Sidecar mode grant (used only when the ledger lives in Salesforce or HubSpot).
insert into public.agent_grants (agent_definition_id, tool, scope, approved_by, approved_at)
select id, 'propose_external_update', '{"all": true}', '00000000-0000-0000-0000-000000000001', now()
from public.agent_definitions where name in ('conversation-capture', 'deal-inspection');

-- Registered evidence sources. Agent-recorded strong evidence must point at one of these.
-- The demo lets agents write strong evidence to these sources so loops can run without a
-- capture integration. In production, set agents_may_write = false and have the integration
-- (service role) write first-hand evidence for agents to cite.
insert into public.evidence_sources (uri_prefix, kinds, description, registered_by, agents_may_write) values
  ('gong://',      array['call_quote'], 'Call recordings', '00000000-0000-0000-0000-000000000001', true),
  ('mail://',      array['email_from_contact','signature_block'], 'Synced mailboxes', '00000000-0000-0000-0000-000000000001', true),
  ('calendar://',  array['meeting_attended'], 'Synced calendars', '00000000-0000-0000-0000-000000000001', true),
  ('telemetry://', array['product_usage'], 'Product telemetry warehouse', '00000000-0000-0000-0000-000000000001', true),
  ('crm://',       array['crm_record'], 'Reports and records in this CRM', '00000000-0000-0000-0000-000000000001', true);
