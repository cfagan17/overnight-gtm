-- Demo signals for one account, so a live loop has something real to reason about.
-- Load after db/seed/seed.sql:  psql "$DSN" -f examples/demo/acme_signals.sql
--
-- Everything here is fictional. In production these rows come from the capture integration
-- (call recorder, mailbox sync, product telemetry), written with the service role, and from
-- people. Agents only cite them.
begin;

-- The West Enterprise rep is called Maya in the explainer video.
update public.sales set first_name = 'Maya', last_name = 'Chen' where email = 'ana.rep@northwind.example';

-- Give Acme Orchards' contacts full names (the generic seed calls them "Contact N").
update public.contacts set first_name = 'Jordan', last_name = 'Lee'  where company_id = 1 and title = 'VP Engineering';
update public.contacts set first_name = 'Priya',  last_name = 'Shah' where company_id = 1 and title = 'Head of Data';
update public.contacts set first_name = 'Casey',  last_name = 'Ruiz' where company_id = 1 and title = 'Director of Procurement';

-- First-hand signals. recorded_by is the capture integration's service identity.
insert into public.evidence (subject_type, subject_id, kind, claim, source_uri, observed_at, strength, recorded_by) values
  ('company', '1', 'product_usage',
   'Trial workspace weekly active users rose from 41 to 87 over the last six weeks.',
   'telemetry://acme-orchards/trial/weekly-active-users', now() - interval '2 days', 'weak', '00000000-0000-0000-0000-0000000000aa'),
  ('company', '1', 'product_usage',
   'Compute credit use in the trial is 2.3 times what it was six weeks ago, mostly scheduled pipeline jobs.',
   'telemetry://acme-orchards/trial/compute-credits', now() - interval '2 days', 'weak', '00000000-0000-0000-0000-0000000000aa'),
  ('contact', (select id::text from public.contacts where company_id = 1 and last_name = 'Shah'), 'call_quote',
   'Priya Shah: "If we can move our pipeline jobs off the homegrown scheduler by Q2, I can make the case to Jordan."',
   'gong://calls/acme-2026-10-21#t=14:05', now() - interval '14 days', 'weak', '00000000-0000-0000-0000-0000000000aa'),
  ('contact', (select id::text from public.contacts where company_id = 1 and last_name = 'Lee'), 'call_quote',
   'Jordan Lee: "My worry is the migration. My team cannot take on another six-month project this year."',
   'gong://calls/acme-2026-10-21#t=31:40', now() - interval '14 days', 'weak', '00000000-0000-0000-0000-0000000000aa'),
  ('contact', (select id::text from public.contacts where company_id = 1 and last_name = 'Ruiz'), 'email_from_contact',
   'Casey Ruiz: "Anything multi-year has to go through our procurement review, which runs about three weeks."',
   'mail://acme-orchards/casey.ruiz/2026-10-28', now() - interval '7 days', 'weak', '00000000-0000-0000-0000-0000000000aa'),
  ('company', '1', 'rep_observation',
   'Maya: Priya asked twice about onboarding help. Jordan skipped the last demo and sent a delegate.',
   'crm://notes/acme-orchards/2026-10-30', now() - interval '5 days', 'weak', '00000000-0000-0000-0000-000000000005'),
  ('company', '1', 'web_page',
   'Acme Orchards posted two data platform engineer roles this month.',
   'https://careers.acmeorchards.example/data-platform', now() - interval '9 days', 'weak', '00000000-0000-0000-0000-0000000000aa');

-- The last plan, and how Maya reviewed it: she kept it but changed the sender to herself.
with d as (
  insert into public.decisions (made_by, "loop", action, subject_type, subject_id, rationale, payload, autonomy_level,
                                status, review_outcome, edited_payload, review_note, reviewed_by, reviewed_at, made_at)
  values ((select ('00000000-0000-0000-0000-0000000001' || lpad(id::text, 2, '0'))::uuid from public.agent_definitions where name = 'account-program'),
          'account_program', 'propose_strategy', 'company', '1',
          'Trial usage is climbing and the Head of Data named a Q2 goal. Propose a usage review, sent by the SDR agent.',
          '{"sender": {"type": "agent", "reason": "Commercial-style first touch"}}', 1,
          'approved', 'edited', '{"sender": {"type": "rep", "reason": "Maya owns the Priya relationship"}}',
          'I own the relationship with Priya. Anything to Acme comes from me, not the agent.',
          '00000000-0000-0000-0000-000000000005', now() - interval '20 days', now() - interval '21 days')
  returning id)
insert into public.strategies (subject_type, subject_id, version, plan, status, decision_id, proposed_by, approved_by, created_at)
select 'company', '1', 1,
  '{"why_now": [{"claim": "Trial usage climbing", "evidence": []}], "sender": {"type": "rep", "reason": "Maya owns the Priya relationship"}}',
  'approved', d.id,
  (select ('00000000-0000-0000-0000-0000000001' || lpad(id::text, 2, '0'))::uuid from public.agent_definitions where name = 'account-program'),
  '00000000-0000-0000-0000-000000000005', now() - interval '21 days'
from d;

commit;
