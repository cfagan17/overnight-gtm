-- How each model and prompt version has performed per loop: runs, decisions,
-- and the share of reviewed decisions accepted as is. Useful when a new model ships.
select r."loop",
       r.model,
       r.prompt_version,
       count(distinct r.id)                                                     as runs,
       count(d.id)                                                              as decisions,
       round(avg((d.review_outcome = 'accepted')::int)
             filter (where d.review_outcome is not null), 2)                    as accepted_as_is
from public.runs r
left join public.decisions d on d.run_id = r.id
group by r."loop", r.model, r.prompt_version
order by r."loop", r.model;
