-- Did the play beat the holdout? Treatment vs holdout rate for every experiment,
-- with the honest range from experiment_result() (difference and 95% interval).
select x.id, x.name, x."loop", x.metric, x.status, public.experiment_result(x.id) as result
from public.experiments x
order by x.id;
