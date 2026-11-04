-- Everything the system knows about why one account is in its current state:
-- evidence, the decisions that cited it, and the plan versions those decisions produced.
-- Replace '1' with your company id (three places).
select 'evidence' as kind, e.id::text as ref, e.observed_at as at, e.strength as detail, e.claim as text
from public.evidence e where e.subject_type = 'company' and e.subject_id = '1'
union all
select 'decision', d.id::text, d.made_at, coalesce(d.review_outcome, d.status), d.rationale
from public.decisions d where d.subject_type = 'company' and d.subject_id = '1'
union all
select 'strategy v' || s.version, s.id::text, s.created_at, s.status, s.plan->>'summary'
from public.strategies s where s.subject_type = 'company' and s.subject_id = '1'
order by at;
