-- Which kinds of evidence show up in decisions that reviewers accepted as is,
-- versus edited or rejected? Kinds that only appear in rejected decisions are a
-- sign a loop is leaning on the wrong signals.
select e.kind,
       e.strength,
       count(*) filter (where d.review_outcome = 'accepted') as in_accepted,
       count(*) filter (where d.review_outcome = 'edited')   as in_edited,
       count(*) filter (where d.review_outcome = 'rejected') as in_rejected
from public.decision_evidence de
join public.decisions d on d.id = de.decision_id
join public.evidence  e on e.id = de.evidence_id
where d.review_outcome is not null
group by e.kind, e.strength
order by in_accepted desc, e.kind;
