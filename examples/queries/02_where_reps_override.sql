-- Where do people keep changing what the agents propose, and what do they write?
-- One row per loop and action, with the edit and rejection rate and recent notes.
select d."loop",
       d.action,
       count(*)                                                        as reviewed,
       round(avg((d.review_outcome <> 'accepted')::int), 2)            as override_rate,
       (array_agg(d.review_note order by d.reviewed_at desc)
          filter (where d.review_note is not null))[1:3]               as recent_notes
from public.decisions d
where d.review_outcome is not null
group by d."loop", d.action
order by override_rate desc, reviewed desc;
