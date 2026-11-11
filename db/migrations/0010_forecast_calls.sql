-- 0010 Forecast calls
--
-- The forecast loop records its call for each segment as inferred evidence on the territory
-- (agents/loops/forecast/loop.yaml). This view gives the latest call per territory with the
-- numbers pulled out of the claim, so a page can put the loop's call next to the human one
-- without holding any logic of its own.
--
-- The numbers are read from the wording the loop is told to use:
--   "Agent forecast call: $1.42M this quarter (range ...). Human call: $1.38M."
-- A claim that does not follow it still shows, with null numbers.
--
-- security_invoker: each person sees only the territories' evidence their own access allows.

create view public.forecast_calls with (security_invoker = on) as
select distinct on (t.id)
       t.id as territory_id, t.name as territory, e.id as evidence_id, e.claim, e.observed_at,
       x.agent_call_usd, x.human_call_usd, x.agent_call_usd - x.human_call_usd as gap_usd
from public.evidence e
join public.territories t on t.id::text = e.subject_id
cross join lateral (
  select (substring(e.claim from 'Agent forecast call: \$([0-9]+(?:\.[0-9]+)?)M'))::numeric * 1000000 as agent_call_usd,
         (substring(e.claim from 'Human call: \$([0-9]+(?:\.[0-9]+)?)M'))::numeric * 1000000 as human_call_usd
) x
where e.subject_type = 'territory' and e.kind = 'inferred' and e.superseded_by is null
  and e.claim like 'Agent forecast call:%'
order by t.id, e.observed_at desc, e.id desc;

revoke all on public.forecast_calls from public, anon;
grant select on public.forecast_calls to authenticated, service_role;
