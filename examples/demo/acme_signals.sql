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
-- Dates are relative to when this file is loaded, including the dates inside the source links,
-- so the signals are always recent. created_at is set to the time of the signal for the same reason.
insert into public.evidence (subject_type, subject_id, kind, claim, source_uri, observed_at, strength, recorded_by, created_at)
select v.subject_type, v.subject_id, v.kind, v.claim,
       replace(v.source_uri, '{date}', to_char(now() - v.age, 'YYYY-MM-DD')), now() - v.age, 'weak', v.recorded_by::uuid, now() - v.age
from (values
  ('company', '1', 'product_usage',
   'Trial workspace weekly active users rose from 41 to 87 over the last six weeks.',
   'telemetry://acme-orchards/trial/weekly-active-users', interval '2 days', '00000000-0000-0000-0000-0000000000aa'),
  ('company', '1', 'product_usage',
   'Compute credit use in the trial is 2.3 times what it was six weeks ago, mostly scheduled pipeline jobs.',
   'telemetry://acme-orchards/trial/compute-credits', interval '2 days', '00000000-0000-0000-0000-0000000000aa'),
  ('contact', (select id::text from public.contacts where company_id = 1 and last_name = 'Shah'), 'call_quote',
   'Priya Shah: "If we can move our pipeline jobs off the homegrown scheduler by Q2, I can make the case to Jordan."',
   'gong://calls/acme-{date}#t=14:05', interval '14 days', '00000000-0000-0000-0000-0000000000aa'),
  ('contact', (select id::text from public.contacts where company_id = 1 and last_name = 'Lee'), 'call_quote',
   'Jordan Lee: "My worry is the migration. My team cannot take on another six-month project this year."',
   'gong://calls/acme-{date}#t=31:40', interval '14 days', '00000000-0000-0000-0000-0000000000aa'),
  ('contact', (select id::text from public.contacts where company_id = 1 and last_name = 'Ruiz'), 'email_from_contact',
   'Casey Ruiz: "Anything multi-year has to go through our procurement review, which runs about three weeks."',
   'mail://acme-orchards/casey.ruiz/{date}', interval '7 days', '00000000-0000-0000-0000-0000000000aa'),
  ('company', '1', 'rep_observation',
   'Maya: Priya asked twice about onboarding help. Jordan skipped the last demo and sent a delegate.',
   'crm://notes/acme-orchards/{date}', interval '5 days', '00000000-0000-0000-0000-000000000005'),
  ('company', '1', 'web_page',
   'Acme Orchards posted two data platform engineer roles this month.',
   'https://careers.acmeorchards.example/data-platform', interval '9 days', '00000000-0000-0000-0000-0000000000aa')
) as v (subject_type, subject_id, kind, claim, source_uri, age, recorded_by);

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
