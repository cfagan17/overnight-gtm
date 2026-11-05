# Check on a real Supabase project, 2026-11-05

Until now everything had been tested on plain Postgres 16, with a small shim standing in for
Supabase. This is the first install on a hosted Supabase project (Postgres 17.11, us-west-1),
using `scripts/install_hosted.py --reset --seed --demo`.

## Install

Atomic CRM's schema, all eight migrations, the Northwind seed and the Acme demo signals applied
cleanly on the first try.

## Test suite against the live project

`EA_HOSTED_DSN=... pytest tests`: on the first run, 71 passed, 3 failed, 7 skipped.
The 7 skipped tests create scratch databases or commit data, so they are not run against a
hosted project. Everything else runs inside transactions that are rolled back.

All three failures had one cause the shim did not model. Supabase grants every new table in
`public` to `anon` and `authenticated` by default. Row-level security still protected the rows
(a rep's delete on the audit log touched 0 rows), but the tables created by these migrations
carried grants they were never meant to have, so a refused write came back as "0 rows" instead
of "permission denied", and the RLS audit flagged 28 tables.

Fixes:
- `0001_ledger.sql` switches the default grants off while the migrations run, and
  `0008_final_grants.sql` switches them back on, so later tables behave as Supabase users expect.
- The test shim now mirrors Supabase's default grants, so local tests catch this. With the shim
  change alone, the same three tests fail locally.
- The same default grants also let any signed-in user call Atomic's `get_user_id_by_email`,
  which Atomic means for the service role only. That is now revoked, with a regression test.
- The Supabase security advisor flagged Atomic's trigger functions as callable through the API.
  Execute on every trigger function in `public` is now revoked from API roles.

After the fixes, on a fresh install: **75 passed, 7 skipped, 0 failed**, including all 15 attacks.

## Supabase security advisor, after the fixes

| Finding | Status |
| --- | --- |
| `init_state` is a security definer view | Atomic's own view. It lets the sign-up page see whether the CRM has been set up, so it reads `sales` with its owner's rights. Accepted as designed upstream |
| Signed-in users can execute security definer functions (the agent and review API) | By design. Each function checks the caller, the run, the grant, the scope and the policies itself, and the tests cover the refused paths |
| `user_invitations` has RLS on and no policies | Deny-all on purpose. Only the service role uses it |
| Leaked password protection is off | A project setting. Turn it on under Authentication in the dashboard |

## A live run on the hosted project

The account program loop ran with `claude-opus-5-5` over the hosted database. It reached the
same conclusions as the run in `examples/live-run/`: Maya as sender, following her edit to v1;
the close date seven days out against a three-week procurement review; the careers page used
only as a question.
