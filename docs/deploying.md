# Deploying on Supabase

Tested on a hosted Supabase project on 2026-11-05 (see `docs/supabase-hosted-check.md`). Use a Supabase branch or a spare project first, run the tests against it, then promote.

## Quick start on a fresh project

```bash
pip install -r requirements.txt
export SUPABASE_DB_URL="postgresql://postgres.<ref>:<db password>@aws-0-<region>.pooler.supabase.com:5432/postgres"   # Connect > Direct > Session pooler
python scripts/install_hosted.py --dsn "$SUPABASE_DB_URL" --seed --demo     # Atomic + migrations + Northwind demo data
EA_HOSTED_DSN="$SUPABASE_DB_URL" pytest tests                                  # runs in rolled-back transactions
```

The connection string needs the database password (Project Settings > Database), not your Supabase account password. Percent-encode any symbols in it.

## Greenfield (Atomic CRM fork)

1. Fork [Atomic CRM](https://github.com/marmelab/atomic-crm) and deploy it as its docs describe (`make supabase-remote-init`).
2. Copy `db/migrations/*.sql` into the fork's `supabase/migrations/` with timestamps after Atomic's latest, keeping their order. Do not copy `db/test-shim/`. Supabase already has everything the shim fakes.
3. `supabase db push`.
4. Fill `public.principals` for your people: role and manager for each. Until you do, Atomic's administrator flag maps to owner and everyone else to rep.
5. Load skills: `python scripts/load_skills.py --dsn "$DATABASE_URL" --owner-uid <your auth user id>`.
6. For each loop you turn on:
   - Create an agent auth user with app metadata `{"ea_kind": "agent"}` (Admin API: `auth.admin.createUser({ email, app_metadata: { ea_kind: "agent" } })`). Atomic requires an invitation row first (`public.user_invitations`).
   - Insert its `principals` row (`kind = 'agent'`, `role = 'agent'`, `agent_definition_id`).
   - Insert `agent_grants` rows for the loop's tools, with a scope (`{"all": true}` or `{"territory_ids": [..]}`) and `approved_at`.
   - Mint a JWT for the agent user and store it where the runner runs.
7. Schedule `select public.take_forecast_snapshot();` weekly with `pg_cron`.
8. Run `tools/rls-audit/rls_audit.py --dsn "$DATABASE_URL"` and review every finding.

## Salesforce sidecar

1. Create a Supabase project. Apply Atomic's schema too, because the primitives reference its `sales` table as the seller directory, then all migrations.
2. Deploy `sidecars/salesforce/metadata` (`sf project deploy start --manifest package.xml`). Assign `EA_Agent_Writer` to one integration user and nothing else.
3. Fill `sidecar_user_map` (Salesforce user id to seller) and `sidecar_territory_map` (territory key to territory).
4. Schedule `sf_sidecar.py ingest` (every few minutes, with `--since` the last run) and `sf_sidecar.py writeback`.
5. Give conversation capture and deal inspection the `propose_external_update` tool instead of `apply_field_update`.

## HubSpot sidecar

The same, with `sidecars/hubspot/`. Create the properties in `properties.json`, use a private app token scoped to the allowlisted properties, and fill the maps with HubSpot owner ids.

## Running loops

Live, over Supabase REST, as the agent:

```bash
python agents/runtime/runner.py --loop account_program --input '{"company_id": 42}' \
  --supabase-url "$SUPABASE_URL" --anon-key "$SUPABASE_ANON_KEY" --jwt "$ACCOUNT_PROGRAM_AGENT_JWT" \
  --model <anthropic model id>
```

Review queue for humans: `public.review_queue()` returns what the signed-in person may approve, and `public.review_decision(...)` records their answer. The console and the Slack digest both use these.

## The console

`console/` is a static Vite app. It needs only the project URL and the publishable (anon) key, because every rule lives in the database.

```bash
cd console
VITE_SUPABASE_URL=https://<project>.supabase.co VITE_SUPABASE_ANON_KEY=<publishable key> npm run build
```

Host `dist/` anywhere. On Vercel, import the repo with the root directory set to `console`; `vercel.json` handles client-side routes. Setting your own URL turns off demo mode: no demo banner and no person switcher.

Turn off public sign-ups in Supabase Auth. Anyone who can sign up gets an `auth.users` row, and while a person with no `sales` or `principals` row sees nothing, there is no reason to allow it.

## Slack

1. Create a Slack app with a bot token (`chat:write`) and Interactivity on.
2. Map people: as an owner, insert rows into `public.slack_user_map (slack_user_id, user_id)`.
3. Each morning after the loops run: `python -m integrations.slack.digest` with `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `SLACK_BOT_TOKEN` and `CONSOLE_URL`. Use `--dry-run` first.
4. Point Interactivity at `python -m integrations.slack.server` (any WSGI host) with `SLACK_SIGNING_SECRET` set.

Only the service role can call `slack_review_queue` and `slack_review_decision`, and both act as the mapped person, so a click in Slack passes exactly the checks a click in the console does. Edits always open the console.

## The public demo

```bash
python scripts/install_hosted.py --dsn "$SUPABASE_DB_URL" --reset --yes-wipe-public-schema --seed --demo --demo-logins
```

This wipes the project and loads Northwind Data with two months of generated history (fixed seed) and the real Claude run in `examples/live-run/`. Every demo person signs in with the password `overnight-demo`. Run it again to reset the demo, for example nightly from cron. Run the test suite against the hosted project only after an install without `--demo`: the tests expect the plain seed.
