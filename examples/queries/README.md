# Ask your own data

The primitives are ordinary Postgres tables, so anyone with read access can ask
questions of them directly, in the Supabase SQL editor, `psql`, a BI tool, or by
asking an AI to write the query. Row-level security still applies: each person
sees only the rows their role allows.

| Query | Question it answers |
| --- | --- |
| `01_evidence_in_accepted_plans.sql` | Which kinds of evidence appear in decisions reviewers accept, edit or reject |
| `02_where_reps_override.sql` | Where people keep overriding the agents, with their notes |
| `03_experiment_readout.sql` | Whether each play beat its holdout, with the 95% range |
| `04_runs_by_model.sql` | How each model and prompt version performed per loop |
| `05_account_story.sql` | The full why behind one account: evidence, decisions, plan versions |

`tests/test_queries.py` runs each of these against the seeded demo database.
