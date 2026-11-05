-- Minimal seed for a STOCK Atomic CRM database (no Overnight migrations).
-- Used only by the attack report to measure the "before" picture. Same people, same
-- account names as seed.sql, so the same attacks can run against both.

begin;
insert into auth.users (id, email, raw_user_meta_data) values
  ('00000000-0000-0000-0000-000000000001', 'riley.ops@northwind.example', '{"first_name":"Riley","last_name":"Ops"}');
insert into public.user_invitations (user_id) values
  ('00000000-0000-0000-0000-000000000005'), ('00000000-0000-0000-0000-000000000007'),
  ('00000000-0000-0000-0000-000000000009'), ('00000000-0000-0000-0000-000000000102');
insert into auth.users (id, email, raw_user_meta_data) values
  ('00000000-0000-0000-0000-000000000005', 'ana.rep@northwind.example', '{"first_name":"Ana","last_name":"West Enterprise AE"}'),
  ('00000000-0000-0000-0000-000000000007', 'cy.rep@northwind.example',  '{"first_name":"Cy","last_name":"East AE"}'),
  ('00000000-0000-0000-0000-000000000009', 'fin.readonly@northwind.example', '{"first_name":"Fin","last_name":"Finance"}'),
  -- In stock Atomic an AI agent connects as an ordinary signed-in user (that is how its MCP server works).
  ('00000000-0000-0000-0000-000000000102', 'account-program@agents.northwind.example', '{"first_name":"Agent","last_name":"Account Program"}');

insert into public.companies (name, state_abbr, country, sales_id)
select 'Acme Orchards', 'CA', 'US', id from public.sales where email = 'ana.rep@northwind.example' union all
select 'Maple Ledger',  'NY', 'US', id from public.sales where email = 'cy.rep@northwind.example';

insert into public.contacts (first_name, last_name, title, company_id, sales_id)
select 'Jordan', 'Contact ' || c.id, 'VP Engineering', c.id, c.sales_id from public.companies c;

insert into public.deals (name, company_id, stage, amount, sales_id)
select c.name || ' - Platform', c.id, 'proposal-sent', 150000, c.sales_id from public.companies c;

insert into public.contact_notes (contact_id, text, sales_id)
select ct.id, 'Call notes: budget approved for Q1', ct.sales_id from public.contacts ct;

insert into public.tasks (contact_id, type, text, sales_id, due_date)
select ct.id, 'call', 'Follow up on pricing', ct.sales_id, now() + interval '3 days' from public.contacts ct;
commit;
